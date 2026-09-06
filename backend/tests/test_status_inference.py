from app.models import ApplicationStatus
from app.services.status_inference import (
    infer_status_from_text,
    refine_suggested_status,
)


def test_ibm_coding_assessment_is_oa_not_phone_screen():
    subject = (
        "Action Required:IBM Coding Assessment for completion "
        "Liam Gelfand - 129919 - 2027 Software Engineering Intern"
    )
    summary = "IBM coding assessment invitation; update status to phone_screen."
    assert infer_status_from_text(subject, summary) == ApplicationStatus.online_assessment
    assert (
        refine_suggested_status(ApplicationStatus.phone_screen, subject, summary)
        == ApplicationStatus.online_assessment
    )


def test_codesignal_and_coderbyte_are_oa():
    assert (
        infer_status_from_text(
            "Solace invited you to complete Solace Associate Software Engineer Assignment on CodeSignal"
        )
        == ApplicationStatus.online_assessment
    )
    assert (
        infer_status_from_text(
            "Entry Level C++ Software Engineer - Technical Assessment via Coderbyte",
            "Wolverine invited you to complete a technical assessment via Coderbyte.",
        )
        == ApplicationStatus.online_assessment
    )


def test_hirevue_and_digital_screen_are_oa():
    assert (
        infer_status_from_text("Reminder to complete your assessment with Shell")
        == ApplicationStatus.online_assessment
    )
    assert (
        infer_status_from_text(
            "Reminder to complete your digital screen for Digital Technology Leadership Program at Carrier Corporation"
        )
        == ApplicationStatus.online_assessment
    )


def test_live_interview_after_assessment_stays_interview():
    subject = (
        "Entry Level C++ Software Engineer (Spring 2027 Graduates) - "
        "Technical Interview Invitation"
    )
    summary = "Wolverine invited you to a technical interview after you passed their assessment."
    assert infer_status_from_text(subject, summary) == ApplicationStatus.interview
    assert (
        refine_suggested_status(ApplicationStatus.interview, subject, summary)
        == ApplicationStatus.interview
    )


def test_rejection_after_assessment_stays_rejected():
    subject = "P&G Careers – Result of your Assessment"
    summary = "P&G rejected the application for IT Engineering role after online assessment."
    assert infer_status_from_text(subject, summary) == ApplicationStatus.rejected
    assert (
        refine_suggested_status(ApplicationStatus.rejected, subject, summary)
        == ApplicationStatus.rejected
    )


def test_null_status_infers_oa():
    assert (
        refine_suggested_status(
            None,
            "P&G Careers - Invitation to Online Assessment",
            "P&G has invited the candidate to complete online assessments.",
        )
        == ApplicationStatus.online_assessment
    )


def test_thank_you_for_applying_is_not_oa():
    assert (
        infer_status_from_text("Thank you for applying to Notion!")
        is None
    )
