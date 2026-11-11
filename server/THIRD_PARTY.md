# Third-party sources

CtS's original server code is covered by the [MIT license](LICENSE). The
third-party components below retain their upstream terms.

The PP-OCRv5 ncnn models and dictionary are fetched from [nihui/ncnn-android-ppocrv5](https://github.com/nihui/ncnn-android-ppocrv5), pinned at revision `458269b48a434a4301070f83f7ce90e8fd11180f`. Individual URLs and SHA-256 values are recorded in `cts_ocr_server/models.json`. The models originate in [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR); its project uses Apache-2.0. Downloaded artifacts retain their upstream terms.

A copy of the [Apache 2.0 license](licenses/Apache-2.0.txt) accompanies the models.

Additional recognition models and dictionaries come from [RapidOCR’s versioned model distribution](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml) and originate in [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR). RapidOCR and PaddleOCR use Apache 2.0. The Docker build converts these models using Tencent’s BSD-3-Clause [pnnx](https://github.com/Tencent/ncnn/tree/master/tools/pnnx). URLs, source revision tags and SHA-256 digests are recorded in `build_models.py`.

The detector preprocessing and postprocessing were adapted from Tencent's [ncnn PP-OCRv5 example](https://github.com/Tencent/ncnn/blob/master/examples/ppocrv5.cpp), copyright 2025 Tencent, SPDX BSD-3-Clause. The ncnn dictionary header retains its upstream license notice. Character decoding/coordinate conversion and the HTTP/client integration are implemented for CtS.

The ncnn BSD-3-Clause notice follows:

Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
Copyright 2025 Tencent.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
