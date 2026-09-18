# Local Image Cleanup Agent

Windows 本機圖片清理與交付工具，適合處理自己擁有或已獲授權修改的客戶素材。圖片處理與 QA 均在電腦上進行。首次安裝會下載 Python 套件與模型；模型備妥後，處理圖片不需要網路。

## 安裝

需求：Windows、Python 3.10、至少 8 GB 可用記憶體，以及模型與輸出所需磁碟空間。GPU 為選用；`setup.ps1` 預設安裝 CPU 版 PyTorch。具備相容的 NVIDIA CUDA 12.4 環境時，可用 `.\setup.ps1 -Cuda124` 安裝 GPU 版，處理命令另加 `--gpu`。

```powershell
.\setup.ps1
.\.venv\Scripts\image-cleanup.exe prepare-models
```

模型會下載到使用者的本機快取。可用 `LOCAL_IMAGE_CLEANUP_MODELS` 指定其他位置。下載完成後會驗證 SHA-256；處理命令只讀取已驗證的模型。

## 處理與 QA

```powershell
.\.venv\Scripts\image-cleanup.exe process --source .\my-images --output .\my-audit --authorized
.\.venv\Scripts\image-cleanup.exe review --source .\my-images --output .\my-audit
```

單張圖片可直接當作 `--source`。輸入與輸出資料夾須分開，原始檔不會覆寫。`review` 只在 `127.0.0.1:8501` 開啟本機 QA 介面；若該埠已被使用，可加 `--port 8502`。

若自動偵測漏掉平台 UI、時間戳或壓字，可在 QA 介面新增矩形區域或上傳與影像同尺寸的黑白遮罩。命令列也支援：

```powershell
.\.venv\Scripts\image-cleanup.exe mark --output .\my-audit --id IMAGE_ID --box 10,20,80,30
.\.venv\Scripts\image-cleanup.exe process --source .\my-images --output .\my-audit --only-id IMAGE_ID --authorized
.\.venv\Scripts\image-cleanup.exe qa --output .\my-audit --id IMAGE_ID --status completed_manual
```

`--detector none --method telea` 可在無模型的環境下測試手動標記流程。正常使用預設 EasyOCR 偵測加 LaMa 修補。自動偵測採保守規則，可能漏掉非文字水印；`completed_auto` 代表程式沒有發現警示，並不代表人工確認無瑕疵。空遮罩、遮罩過大、低信心、疑似殘留、手動區域和處理失敗會進入待複查。

每張圖在輸出資料夾保留完整原圖副本、遮罩、修補圖、對照圖；`report.csv` 和 `report.json` 使用相對路徑。重新執行相同命令會跳過未變動項目，並保留人工 QA 紀錄。若影像或標記變更，新結果會重新進入待複查。

## 客戶交付

```powershell
.\.venv\Scripts\image-cleanup.exe export --output .\my-audit
```

輸出 `client_delivery.zip`，內含已完成圖片、縮圖對照 PPTX、成果總表 XLSX，以及 CSV/JSON。需複查、不完美和失敗項目仍列於總表，但不作為完成成果交付。ZIP 不含完整原始檔；PPTX 的縮圖對照仍會呈現縮小的處理前畫面。交付檔移除圖片 EXIF，使用穩定 ID，不寫入原始檔名或電腦絕對路徑。請在交付客戶前檢查圖片內容本身是否仍含敏感資訊。

## 發行與授權

產品程式碼依 [AGPL-3.0](LICENSE) 發行。第三方依賴與模型來源見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。模型權重、客戶素材、測試輸出、虛擬環境與本機日誌不屬於原始碼發行內容。此 Skill 保留本機 Agent 可讀的 `SKILL.md`；目前未在 Capafy 上架。
