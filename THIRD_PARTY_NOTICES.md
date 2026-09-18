# Third-party notices

This project downloads Python packages during setup. Their source and license information:

| Component | Purpose | License / source |
| --- | --- | --- |
| EasyOCR 1.7.2 | Local text detection | [Apache-2.0](https://github.com/JaidedAI/EasyOCR/blob/master/LICENSE) |
| simple-lama-inpainting 0.1.2 | Local image inpainting | [Apache-2.0](https://github.com/enesmsahin/simple-lama-inpainting/blob/main/LICENSE) |
| Big-LaMa TorchScript model | Local inpainting weights, downloaded on setup | [Apache-2.0 model card](https://huggingface.co/JosephCatrambone/big-lama-torchscript/tree/7dfbdc6dc27602d370909e8688f8f84404a1f995) |
| EasyOCR CRAFT and English weights | Local OCR, downloaded by upstream package on setup | [EasyOCR model configuration](https://github.com/JaidedAI/EasyOCR/blob/master/easyocr/config.py); separate weight terms were not found, so weights are not redistributed |
| OpenCV | Image processing | [Apache-2.0](https://github.com/opencv/opencv/blob/4.x/LICENSE) |
| Pillow | Image I/O | [HPND](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| NumPy | Arrays | [BSD-3-Clause and bundled notices](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| PyTorch | Tensor runtime | [BSD-3-Clause](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| python-pptx | PowerPoint export | [MIT](https://github.com/scanny/python-pptx/blob/master/LICENSE) |
| openpyxl | Workbook export | [MIT](https://foss.heptapod.net/openpyxl/openpyxl/-/blob/branch/default/LICENCE.rst) |
| Streamlit | Local review UI | [Apache-2.0](https://github.com/streamlit/streamlit/blob/develop/LICENSE) |

No model weights or third-party source trees are distributed in this repository. The installer verifies each downloaded model with the SHA-256 values in `image_cleanup/models.py`. The product code is AGPL-3.0; third-party packages retain their own licenses.
