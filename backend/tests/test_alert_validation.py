import pytest

from app.routers.inventory import validate_alert_text


@pytest.mark.parametrize(
    ("title", "message"),
    [
        ("Deficit Notice", "Deficit in Emergency Department: 2 units required."),
        ("Surplus Notice", "Surplus in Ward Alpha: 3 units available for transfer."),
        ("PAR deficit", "Usable count (0) is below PAR (5) in Ward A."),
        ("PAR deficit", "Deficit in Ward B. Infusion Pump required."),
        ("Operational Notice", "Equipment staged at Nurse Station for cleaning."),
        ("Storage Deficit", "Critical care inventory low in Central Supply."),
        ("Rebalance", "Recommended transfer to Operating Room."),
    ],
)
def test_legitimate_facility_and_zone_phrases_are_accepted(title: str, message: str) -> None:
    validate_alert_text(title, message)


@pytest.mark.parametrize(
    ("title", "message"),
    [
        ("Theft Alert", "Possible theft in Ward A"),
        ("Hoarding Warning", "Stop hoarding infusion pumps"),
        ("Staff Notice", "Staff is lazy and neglected maintenance"),
        ("Negligent Care", "Equipment handling was negligent"),
        ("Missing Pump", "Infusion pump was stolen from storage"),
        ("Hoarder Alert", "Unit hoarder holding extra pumps"),
        ("Neglect Alert", "Apparent neglect of clean pumps"),
    ],
)
def test_prohibited_terms_are_rejected(title: str, message: str) -> None:
    with pytest.raises(ValueError, match="prohibited term"):
        validate_alert_text(title, message)


@pytest.mark.parametrize(
    ("title", "message"),
    [
        ("Contact Supervisor", "Call John Smith immediately"),
        ("Doctor Request", "Dr. Rao requested two infusion pumps"),
        ("Doctor Request", "Dr Rao requested two infusion pumps"),
        ("Doctor Request", "Doctor Smith ordered new pumps"),
        ("Nurse Request", "Nurse Priya requested urgent equipment"),
        ("Review Needed", "Alex Smith review required"),
        ("Staff Notice", "Nurse Emily transferred the pump"),
        ("Contact Tech", "Please contact Mr. Davis for repair"),
    ],
)
def test_person_names_and_titles_are_rejected(title: str, message: str) -> None:
    with pytest.raises(ValueError, match="individual's name"):
        validate_alert_text(title, message)

