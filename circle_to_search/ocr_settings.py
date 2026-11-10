"""Native connection settings for local and self-hosted text recognition."""

from PySide6.QtCore import QThreadPool,QTimer,Qt,Signal
from PySide6.QtWidgets import QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QScrollArea,QSpinBox,QVBoxLayout,QWidget,QFrame

from .appearance import current_theme
from .ocr_backend import OcrConfig,check_server,configure_ocr,current_config
from .workers import Task


class OcrSettingsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Text recognition')
        self.setMinimumWidth(540)
        self.setStyleSheet('QDialog {background:'+current_theme().background+';}')
        self.config=current_config()
        self.checking=False
        layout=QVBoxLayout(self)
        description=QLabel('Choose where CtS recognizes text. Local GPU mode manages a CtS backend on this computer; server mode connects to your own CtS backend on another device.')
        description.setWordWrap(True)
        layout.addWidget(description)
        form=QFormLayout()
        self.backend=QComboBox()
        self.backend.addItem('Local GPU (managed by CtS)','gpu')
        self.backend.addItem('Self-hosted CtS server','server')
        self.backend.addItem('Local Tesseract (CPU)','local')
        self.backend.setCurrentIndex(self.backend.findData(self.config.backend))
        form.addRow('Backend',self.backend)
        self.gpu=QLineEdit(self.config.local_gpu_name)
        self.gpu.setPlaceholderText('Automatic, or a name such as AMD / Intel')
        form.addRow('Local GPU',self.gpu)
        self.url=QLineEdit(self.config.server_url)
        self.url.setPlaceholderText('http://127.0.0.1:8766')
        form.addRow('Server address',self.url)
        self.token=QLineEdit(self.config.token)
        self.token.setEchoMode(QLineEdit.Password)
        form.addRow('Server token',self.token)
        self.timeout=QSpinBox()
        self.timeout.setRange(1,120)
        self.timeout.setSuffix(' seconds')
        self.timeout.setValue(round(self.config.timeout))
        form.addRow('Timeout',self.timeout)
        self.fallback=QCheckBox('Use local Tesseract if the server is unavailable')
        self.fallback.setChecked(self.config.fallback)
        form.addRow(self.fallback)
        layout.addLayout(form)
        self.privacy=QLabel('Server mode sends the frozen monitor image and selection crops to the configured server. Google searches still receive only the selected text or crop.')
        self.privacy.setWordWrap(True)
        layout.addWidget(self.privacy)
        self.test=QPushButton('Check connection')
        self.test.clicked.connect(self.check_connection)
        self.pending_save=False
        layout.addWidget(self.test)
        self.status=QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.rejected.connect(self.cancel_pending_save)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.buttons=buttons
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.backend.currentIndexChanged.connect(self.update_enabled)
        self.update_enabled()

    def update_enabled(self):
        mode=self.backend.currentData()
        self.backend.setEnabled(not self.checking)
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not self.checking)
        for control in (self.url,self.token):control.setEnabled(mode=='server' and not self.checking)
        self.gpu.setEnabled(mode=='gpu' and not self.checking)
        for control in (self.timeout,self.fallback,self.test):control.setEnabled(mode!='local' and not self.checking)
        self.test.setText('Set up / check local GPU' if mode=='gpu' else 'Check server connection')
        self.privacy.setText('Local GPU mode keeps OCR on this computer. CtS uses Docker to install and start its backend; first-time setup downloads the models.' if mode=='gpu' else
            'Server mode sends the frozen monitor image and selection crops to your configured CtS backend.' if mode=='server' else
            'Local Tesseract runs on this computer’s CPU. No OCR images are sent to a server.')

    def values(self):
        return OcrConfig(self.backend.currentData(),self.url.text().strip(),self.token.text().strip(),self.timeout.value(),
                         self.fallback.isChecked(),self.gpu.text().strip()).validated()

    def check_connection(self):
        try:config=self.values()
        except ValueError as error:
            self.status.setText(str(error));return
        self.checked_config=config
        self.status.setText('Preparing local text recognition…' if config.backend=='gpu' else 'Connecting…')
        self.checking=True
        self.update_enabled()
        if config.backend=='gpu':
            from .managed_ocr import prepare_local
            self.task=Task(prepare_local,config)
        else:self.task=Task(check_server,config)
        self.task.signals.done.connect(self.server_checked)
        self.task.signals.failed.connect(self.server_failed)
        QThreadPool.globalInstance().start(self.task)

    def cancel_pending_save(self):
        self.pending_save=False

    def server_checked(self,info):
        self.checking=False
        kind='Vulkan GPU' if info.get('accelerated') else 'CPU reference mode'
        self.status.setText('Connected: '+str(info.get('device','unknown device'))+' ('+kind+'). Character selection is supported.')
        self.update_enabled()
        if self.pending_save:
            self.pending_save=False
            self.persist(self.checked_config)

    def server_failed(self,message):
        self.checking=False
        self.pending_save=False
        self.status.setText(message)
        self.update_enabled()

    def save_settings(self):
        try:config=self.values()
        except ValueError as error:
            self.status.setText(str(error));return
        if config.backend=='gpu':
            self.pending_save=True
            self.check_connection()
        else:self.persist(config)

    def persist(self,config):
        try:config.save()
        except (OSError,ValueError) as error:
            self.status.setText(str(error));return
        configure_ocr(config)
        self.accept()


class OcrSettingsPanel(QWidget):
    """Keep settings in the same Wayland layer surface as the selection UI.

    An application-modal xdg dialog can be below Plasma's overlay layer and
    block the window that covers it. This child panel needs no native dialog
    surface or application-wide modal input grab.
    """
    finished=Signal(int)

    def __init__(self,parent):
        super().__init__(parent)
        self.setObjectName('ocrSettingsCover')
        self.completed=False
        self.setAttribute(Qt.WA_NoMousePropagation)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setCursor(Qt.ArrowCursor)
        self.setStyleSheet('QWidget#ocrSettingsCover {background:rgba(0,0,0,120);}')
        self.dialog=OcrSettingsDialog(self)
        self.dialog.setWindowFlags(Qt.Widget)
        self.dialog.setModal(False)
        heading=QLabel('Text recognition')
        heading.setStyleSheet('font-size:19px;font-weight:600;')
        self.dialog.layout().insertWidget(0,heading)
        self.scroll=QScrollArea(self)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.dialog)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(24,24,24,24)
        layout.addStretch()
        row=QHBoxLayout()
        row.addStretch();row.addWidget(self.scroll);row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        self.dialog.finished.connect(self.finish)
        self.setGeometry(parent.rect())

    def resizeEvent(self,event):
        super().resizeEvent(event)
        width=max(1,min(620,self.width()-48))
        self.dialog.setMinimumWidth(min(540,width))
        self.scroll.setFixedSize(width,max(1,min(self.dialog.sizeHint().height(),self.height()-48)))

    def present(self):
        self.show()
        self.raise_()
        # The triggering menu releases its focus/mouse grab after its action
        # returns. Give focus to the settings control on the next event turn.
        QTimer.singleShot(0,self.dialog.backend,lambda:self.dialog.backend.setFocus(Qt.OtherFocusReason))

    def finish(self,result):
        if self.completed:return
        self.completed=True
        self.hide()
        self.finished.emit(result)
        self.deleteLater()
