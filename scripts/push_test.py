import asyncio

from work_researcher import drive
from work_researcher.config import load_settings


async def main():
    s = load_settings()
    path = s.cv_dir / "Andrew_Remniow_CV_2025.pdf"
    result = await drive.upload_cv(s, path)
    print("push result:", result)
    listing = await drive.list_files(s)
    print("folder:", listing.get("folder", {}).get("name"),
          "| files:", len(listing.get("files", [])))


asyncio.run(main())
