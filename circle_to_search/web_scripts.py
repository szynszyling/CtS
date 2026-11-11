"""Keep Google's result content underneath the app's stable search controls."""

import json

from .appearance import DARK


def translate_dark_palette(theme):
    # Translate's native dark palette provider declares these Material tokens.
    # Override its neutral surfaces at that provider, after its own theme switch,
    # so dark icons/controls still use Google's native states and illustrations.
    tokens = {
        "background": theme.background,
        "surface": theme.background,
        "surface-dim": theme.background,
        "surface-container-lowest": theme.background,
        "surface-container-low": theme.background,
        "surface-container": theme.surface,
        "surface-container-high": theme.hover,
        "surface-container-highest": theme.pressed,
        "surface-bright": theme.hover,
        "surface-variant": theme.border,
        "on-surface": theme.text,
        "on-surface-variant": theme.muted,
        "outline": theme.muted,
        "outline-variant": theme.border,
    }
    declarations = []
    for name, color in tokens.items():
        rgb = ",".join(str(int(color[index : index + 2], 16)) for index in (1, 3, 5))
        declarations.extend(
            (
                f"--gm3-sys-color-{name}:{color}!important;",
                f"--gm3-sys-color-{name}-rgb:{rgb}!important;",
            )
        )
    return (
        "@media(prefers-color-scheme:dark){.v1vOZe,.v1vOZe #gb{" + "".join(declarations) + "}"
        '.v1vOZe :is(#gb,header,[role="banner"]){background:'
        + theme.background
        + "!important;"
        + "--og-bar-background:"
        + theme.background
        + "!important;}}"
    )


SEARCH_CHROME = r"""(() => {
    if (!['www.google.com','google.com','lens.google.com'].includes(location.hostname) || location.pathname!=='/search') return;
    const style=document.createElement('style');
    style.id='cts-search-chrome';
    const aiMode=new URL(location.href).searchParams.get('udm')==='50';
    style.textContent=`#sfcnt,#searchform,#gb,#top_nav,#hdtb,#appbar,#hdtb-tls{display:none!important}
        body{margin:0!important;padding-top:0!important} #cnt{padding-top:0!important}`;
    // AI Mode places its answer before the ordinary #rcnt result container.
    // Only regular Search uses those sibling nodes as disposable spacers.
    style.textContent+=aiMode ? 'body > header{display:none!important}' :
        'body > :is(div,span):has(~ #main):not([role="main"]):not(:has([role="main"])),#cnt > div:has(~ #rcnt):not([role="main"]):not(:has([role="main"])){display:none!important}';
    document.head.appendChild(style);
    const names=new Set(['ai mode','all','images','videos','shopping','news','forums','maps','books','web','more','tools','search tools','exact matches','visual matches','feedback',
        'tryb ai','wszystko','grafika','wideo','zakupy','wiadomości','fora','mapy','książki','sieć','więcej','narzędzia','dokładne dopasowania','dopasowania wizualne']);
    const name=a=>a.textContent.trim().toLowerCase().replace(/\s+/g,' ');
    function hideTabs() {
        const links=[...document.querySelectorAll('a[href]')].filter(a=>names.has(name(a)));
        for(const link of links) {
            const rect=link.getBoundingClientRect();
            if(!rect.width || rect.top+scrollY>350) continue;
            for(let row=link.parentElement;row && row!==document.body;row=row.parentElement) {
                const bounds=row.getBoundingClientRect();
                if(bounds.height>150) break;
                const tabs=new Set([...row.querySelectorAll('a[href]')].map(name).filter(n=>names.has(n)));
                if(tabs.size>=3) {row.style.display='none';break;}
            }
            const semantic=link.closest('nav,[role="navigation"],[role="tablist"]');
            if(semantic && semantic.getBoundingClientRect().height<150) semantic.style.display='none';
        }
    }
    hideTabs();
    let queued=false;
    new MutationObserver(()=>{
        if(queued)return;
        queued=true;
        requestAnimationFrame(()=>{queued=false;hideTabs();});
    }).observe(document.documentElement,{childList:true,subtree:true});
})();"""

TRANSLATE_CHROME = r"""(() => {
    if(location.hostname!=='translate.google.com')return;
    const themeSelector='[aria-label="Switch between light and dark theme"]';
    const selector='[aria-label="Google apps"],a[href*="accounts.google.com/ServiceLogin"],a[href*="accounts.google.com/v3/signin"],'+themeSelector;
    const style=document.createElement('style');
    style.textContent=selector+'{display:none!important}'+CTS_TRANSLATE_PALETTE;
    document.head.appendChild(style);
    function cleanHeader() {
        for(const header of document.querySelectorAll('#gb,header,[role="banner"]')) {
            for(const control of header.querySelectorAll('a,button,[role="button"]')) {
                const label=(control.getAttribute('aria-label') || control.textContent).trim().toLowerCase();
                if(['sign in','google apps','zaloguj się','aplikacje google'].includes(label))
                    control.style.setProperty('display','none','important');
            }
        }
    }
    const preference=matchMedia('(prefers-color-scheme:dark)');
    let pending=false,lastToggle=0,retries=0;
    function synchronizeTheme() {
        if(pending)return;
        pending=true;
        setTimeout(()=>{
            pending=false;
            if(!document.body)return;
            const color=getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g);
            if(!color || (color.length===4 && Number(color[3])===0))return;
            const dark=color.slice(0,3).reduce((sum,c)=>sum+Number(c),0)<384;
            if(dark===preference.matches){retries=0;return;}
            const toggle=document.querySelector(themeSelector);
            // Translate has its own stored appearance rather than following
            // the browser hint. Use its native switch, retaining all its dark
            // styles, icons, menus and translation input colors.
            if(toggle && Date.now()-lastToggle>1000 && retries<6){
                lastToggle=Date.now();retries++;toggle.click();
            }
            if(retries<6)synchronizeTheme();
        },250);
    }
    cleanHeader();
    synchronizeTheme();
    preference.addEventListener('change',()=>{retries=0;synchronizeTheme();});
    new MutationObserver(()=>{cleanHeader();synchronizeTheme();}).observe(document.documentElement,{childList:true,subtree:true});
})();""".replace("CTS_TRANSLATE_PALETTE", json.dumps(translate_dark_palette(DARK)))


# Google's basic verification/error document has no native dark stylesheet.
# Theme its surrounding document without altering isolated challenge frames.
SERVICE_THEME = r"""(() => {
    if(!['www.google.com','google.com'].includes(location.hostname) || !location.pathname.startsWith('/sorry'))return;
    const style=document.createElement('style');
    style.textContent=`@media(prefers-color-scheme:dark){
        html,body{background:#22242a!important;color:#e8eaed!important;color-scheme:dark}
        a{color:#8ab4f8}
    }`;
    document.head.appendChild(style);
})();"""
