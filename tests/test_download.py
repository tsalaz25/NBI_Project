#Link-finding tests against HTML shaped like FHWA's pages.
from src import download

YEAR_PAGE = """
<a href="https://www.fhwa.dot.gov/bridge/nbi/disclaim.cfm?nbiYear=2024nodel&amp;nbiZip=zip">zip</a>
<a href="https://www.fhwa.dot.gov/bridge/nbi/disclaim.cfm?nbiYear=2024del&amp;nbiZip=zip">zip</a>
<a href="https://www.fhwa.dot.gov/bridge/nbi/disclaim.cfm?nbiYear=2024&amp;nbiState=NM24">New Mexico</a>
<a href="https://www.fhwa.dot.gov/bridge/nbi/disclaim.cfm?nbiYear=2024/delimited&amp;nbiState=NM24">New Mexico</a>
"""
DISCLAIMER = '<a href="https://www.fhwa.dot.gov/bridge/nbi/2024/delimited/NM24.txt">Proceed to Data</a>'
BASE = "https://www.fhwa.dot.gov/bridge/nbi/ascii2024.cfm"


def test_finds_per_state_delimited_link_not_the_no_delimiter_one():
    links = download.extract_links(YEAR_PAGE, BASE)
    got = download.find_state_delimited_link(links, 2024, "NM")
    assert got.endswith("nbiYear=2024/delimited&nbiState=NM24")


def test_finds_all_states_delimited_zip_fallback():
    links = download.extract_links(YEAR_PAGE, BASE)
    got = download.find_all_states_delimited_zip(links, 2024)
    assert "nbiYear=2024del&" in got


def test_follows_disclaimer_to_data_file():
    links = download.extract_links(DISCLAIMER, BASE)
    assert download.find_data_link(links).endswith("/2024/delimited/NM24.txt")


def test_relative_links_are_made_absolute():
    links = download.extract_links('<a href="2024/delimited/NM24.txt">x</a>', BASE)
    assert links == ["https://www.fhwa.dot.gov/bridge/nbi/2024/delimited/NM24.txt"]
