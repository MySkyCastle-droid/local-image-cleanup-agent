---
name: local-image-cleanup
description: Clean authorized local images in batches with visible masks, QA decisions, and client delivery files. Use for Windows image cleanup where source media must stay on the user's computer.
---

# Local Image Cleanup

Use this skill only for images the user owns or is authorized to modify. Confirm that authorization before processing. The local command is `image-cleanup`; see `README.md` for installation and commands.

1. Ask for a local source folder and a separate output folder. Run `image-cleanup process --source <folder> --output <folder> --authorized`.
2. Report counts and the local review URL or report path. Do not read source images into the agent context, attach them to chat, or upload them to a service. Do not print image filenames or OCR text in chat.
3. For missed platform UI, timestamps, or overlaid text, use `image-cleanup mark --output <folder> --id <id> --box x,y,width,height` and rerun only that item. Review the mask and comparison locally before approving it.
4. Use `image-cleanup qa --output <folder> --id <id> --status completed_manual|imperfect|needs_review` for human decisions. Use `image-cleanup export --output <folder>` only when the user asks for a client package.

Treat `completed_auto` as an automated judgment, never as a human inspection. Keep failures and uncertain results visible. Do not imply that an undetected watermark is proven absent. The source files are never overwritten.
