# Parser Tests
import pandas as pd
from src import parse

def test_headers_resolve_by_item_suffix():
    cols = ["STATE_CODE_001", "STRUCTURE_KIND_043A", "BC01_DECK_058", "FED_AGENCY"]
    got = parse.index_headers(cols)
    assert got["001"] == "STATE_CODE_001"
    assert got["043A"] == "STRUCTURE_KIND_043A"
    assert got["058"] == "BC01_DECK_058"
    assert "FED_AGENCY" not in got.values()

def test_inspection_dates_without_leading_zero():
    s = pd.Series(["222", "1122", "124", "895", "", "1399", "1226", " 923 "])
    got = parse.parse_inspection_date(s, year=2024)
    assert got[0] == pd.Timestamp("2022-02-01")   # 3 digits: Feb 2022
    assert got[1] == pd.Timestamp("2022-11-01")
    assert got[2] == pd.Timestamp("2024-01-01")
    assert got[3] == pd.Timestamp("1995-08-01")
    assert pd.isna(got[4])                        # blank
    assert pd.isna(got[5])                        # month 13
    assert pd.isna(got[6])                        # after the report year
    assert got[7] == pd.Timestamp("2023-09-01")   # whitespace tolerated

def test_parse_file_counts_everything_it_drops(tmp_path):
    f = tmp_path / "NM24.txt"
    f.write_text(
        "STATE_CODE_001,STRUCTURE_NUMBER_008,YEAR_BUILT_027,DECK_COND_058,"
        "SUPERSTRUCTURE_COND_059,SUBSTRUCTURE_COND_060,CULVERT_COND_062,DATE_OF_INSPECT_090\n"
        "35,       0401-BA1,1995,6,7,7,N,1122\n"      # padded structure number
        "35,000000000001034,1993,N,N,N,7,723\n"       # culvert
        "35,       0401-BA1,1995,6,7,7,N,1122\n"      # duplicate -> rejected
        "35,,1990,5,5,5,N,1022\n"                     # no structure number -> rejected
        "35,000000000009999,1980,5,5,5,N,\n"          # undated
        "35,TOO,MANY,FIELDS,1,2,3,4,5,6,7,8\n",       # malformed
        encoding="latin-1",
    )
    r = parse.parse_file(f, 2024, "NM")
    assert r.rows_malformed == 1
    assert r.rows_rejected == 2
    assert r.rows_undated == 1
    assert set(r.frame["asset_id"]) == {"NM-0401-BA1", "NM-000000000001034", "NM-000000000009999"}
    culvert = r.frame.set_index("asset_id").loc["NM-000000000001034"]
    assert pd.isna(culvert["cond_deck"]) and culvert["cond_culvert"] == 7
    assert "main_unit_spans(045)" in r.columns_missing


def test_foot_mark_apostrophe_does_not_merge_rows(tmp_path):

    # 2009 Line SHape: Location Field is wrapped in apostrophes
    # AND contains 1 as a Foot Mark. A strict reader merges this row
    # the file's Line Count Checked

    f = tmp_path / "NM09.txt"
    f.write_text(
        "STATE_CODE_001,STRUCTURE_NUMBER_008,RECORD_TYPE_005A,LOCATION_009,"
        "DECK_COND_058,DATE_OF_INSPECT_090\n"
        "35,000000000002367,1,'500' E OF WASHINGTION AVE',6,1108\n"
        "35,000000000002391,1,'50' N OF 7TH STREET      ',7,908\n"
        "35,000000000002400,1,'NEAR MP 12',5,708\n",
        encoding="latin-1",
    )
    r = parse.parse_file(f, 2009, "NM")
    assert r.data_lines == 3
    assert r.rows_read == 3
    assert r.rows_malformed == 0
    got = r.frame.set_index("asset_id")["cond_deck"].to_dict()
    assert got == {"NM-000000000002367": 6, "NM-000000000002391": 7, "NM-000000000002400": 5}


def test_route_under_records_are_filtered_before_deduplication(tmp_path):

    # The Route-Under record comes 1st and has different rating
    # Keeping "the first duplicate" picks the wrong record

    f = tmp_path / "NM05.txt"
    f.write_text(
        "STATE_CODE_001,STRUCTURE_NUMBER_008,RECORD_TYPE_005A,DECK_COND_058,DATE_OF_INSPECT_090\n"
        "35,000000000000777,2,3,\n"
        "35,000000000000777,A,4,\n"
        "35,000000000000777,1,8,605\n",
        encoding="latin-1",
    )
    r = parse.parse_file(f, 2005, "NM")
    assert r.rows_route_under == 2
    assert r.rows_rejected == 0
    assert r.rows_undated == 0
    assert r.frame["cond_deck"].tolist() == [8]
