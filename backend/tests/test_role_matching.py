from app.services.suggestion_service import (
    _titles_match,
    extract_job_id,
)


def test_extract_ibm_job_ids():
    subj = (
        "Action Required:IBM Coding Assessment for completion "
        "Liam Gelfand - 128506 - Software Developer Spring Co-op 2027"
    )
    assert extract_job_id(subj) == "128506"
    subj2 = (
        "Action Required:IBM Coding Assessment for completion "
        "Liam Gelfand - 128340 - Technical Sales Engineer - Entry-Level Sales Program 2027"
    )
    assert extract_job_id(subj2) == "128340"


def test_titles_do_not_collapse_distinct_ibm_roles():
    assert not _titles_match(
        "Intern Conversion: Software Developer",
        "Software Developer Spring Co-op 2027",
    )
    assert not _titles_match(
        "Software Developer Spring Co-op 2027",
        "Technical Sales Engineer - Entry-Level Sales Program 2027",
    )
    assert _titles_match(
        "Software Developer Spring Co-op 2027",
        "Software Developer Spring Co-op 2027",
    )
