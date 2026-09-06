from app.models import ApplicationStatus
from app.services.email.subject_fastpath import try_fastpath


def test_ibm_coding_assessment_fastpath():
    hit = try_fastpath(
        "Action Required:IBM Coding Assessment for completion "
        "Liam Gelfand - 129919 - 2027 Software Engineering Intern",
        "",
        "IBM Talent Acquisition <talent@ibm.com>",
    )
    assert hit is not None
    assert hit["suggested_status"] == ApplicationStatus.online_assessment.value
    assert hit["company"] == "IBM"
    assert "Software Engineering Intern" in (hit["title"] or "")


def test_codesignal_and_hirevue_fastpath():
    codesignal = try_fastpath(
        "Solace invited you to complete Solace Associate Software Engineer Assignment on CodeSignal",
        "",
        "CodeSignal <no-reply@codesignal.com>",
    )
    assert codesignal is not None
    assert codesignal["suggested_status"] == ApplicationStatus.online_assessment.value
    assert codesignal["company"] == "Solace"

    hirevue = try_fastpath(
        "You are invited to complete an assessment with Shell - R205157",
        "",
        "HireVue Invitation <noreply@mail.hirevue-app.eu>",
    )
    assert hirevue is not None
    assert hirevue["suggested_status"] == ApplicationStatus.online_assessment.value
    assert hirevue["company"] == "Shell"


def test_thank_you_for_applying_is_still_applied():
    hit = try_fastpath(
        "Thank you for applying to Notion!",
        "Thanks for your application for the Software Engineer role.",
        "Notion Recruiting <jobs@notion.so>",
    )
    assert hit is not None
    assert hit["suggested_status"] == ApplicationStatus.applied.value


def test_assessment_result_is_not_oa_fastpath():
    hit = try_fastpath(
        "P&G Careers – Result of your Assessment",
        "Unfortunately we will not be moving forward.",
        "P&G Workday System <pgworkdaysystem.im@pg.com>",
    )
    assert hit is None or hit["suggested_status"] != ApplicationStatus.online_assessment.value
