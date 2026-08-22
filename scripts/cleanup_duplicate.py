import asyncio

from work_researcher import drive
from work_researcher.config import load_settings


async def main():
    s = load_settings()
    # remove the duplicate created by the buggy push test (identical content,
    # created seconds ago with a known id)
    dup_id = "1WZ383zvy5KAT1hIavO4h5gvY8SgPSKXS"

    def _delete():
        service = drive.build_service(s)
        f = service.files().get(fileId=dup_id).execute()
        assert f["name"] == "Andrew_Remniow_CV_2025.pdf", f
        service.files().delete(fileId=dup_id).execute()
        return f["name"]

    name = await asyncio.to_thread(_delete)
    print("deleted duplicate:", name)
    listing = await drive.list_files(s)
    print("folder files now:", len(listing["files"]))


asyncio.run(main())
