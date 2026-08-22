import asyncio

from work_researcher import geo
from work_researcher.config import load_settings
from work_researcher.persistence import connect


async def main():
    s = load_settings()
    async with connect(s.db_path) as conn:
        home = await geo.home_geo(s, conn)
        print("home:", home)
        for place in ["Glasgow (G1)", "Stirling (FK7)", "Crawley (RH10)",
                      "Manchester, Greater Manchester", "Reading, Berkshire",
                      "London", "Aberdeen"]:
            g = await geo.geocode(s, place, conn)
            if g and home:
                ev = geo.evaluate_location(
                    work_mode="on_site", job_lat=g["lat"], job_lon=g["lon"],
                    job_location=place, home_lat=home["lat"], home_lon=home["lon"],
                    home_location="Blackpool", max_commute_miles=40,
                    willing_to_relocate=False)
                print(f"{place:35} -> {g['name']:20} {ev['distance_miles']}mi "
                      f"{ev['location_status']}")
            else:
                print(f"{place:35} -> NOT RESOLVED")
        await conn.commit()


asyncio.run(main())
