"""
Unit tests for appointment tool executors in agents/tools/navigation_tools.py.

All external dependencies (RecommendationStore, AppointmentAgentClient) are mocked.
No real HTTP calls to the external Appointment Agent are made.

Test coverage (planned):
  - execute_check_availability
      - happy path (valid recommendation_id and provider_id)
      - invalid recommendation_id
      - provider_id not in recommendation
      - HTTP error from AppointmentAgentClient
      - care_type and specialty extraction from CareDecision
      - patient_context built correctly with location and preferences
  - execute_book_appointment
      - happy path (valid parameters)
      - invalid recommendation_id
      - provider_id not authorized
      - BookingRequest includes recommendation_id (internal field)
      - specialty extraction from CareDecision
      - HTTP error from AppointmentAgentClient
  - execute_reschedule_appointment
      - Workflow A (new_slot_id provided)
      - Workflow B (preferred_date/time provided)
      - neither new_slot_id nor preferences provided
      - HTTP error from AppointmentAgentClient
  - execute_cancel_appointment
      - happy path (valid parameters)
      - HTTP error from AppointmentAgentClient
  - Tool registry and definitions
      - ALL_TOOLS contains appointment tool definitions
      - _TOOL_REGISTRY maps appointment tool names to executors
      - execute_tool dispatches to appointment executors
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.alternate_care.models.schemas import (
    CareDecision,
    ProviderCandidate,
    Recommendation,
    AppointmentSlot,
    PatientLocation,
)
from app.services.alternate_care.appointment.schemas import (
    AppointmentConfirmation,
    AppointmentStatusResponse,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

class MockRecommendationStore:
    """Mock implementation of RecommendationStore for testing.
    
    Provides require() and require_provider() methods that return
    test data without actual storage.
    """
    
    def __init__(self):
        self._recommendations = {}
        self._patient_locations = {}
    
    def add_recommendation(
        self,
        recommendation_id: str,
        recommendation: Recommendation,
        patient_location: Optional[PatientLocation] = None,
    ) -> None:
        """Add a recommendation to the mock store for testing."""
        self._recommendations[recommendation_id] = recommendation
        if patient_location:
            self._patient_locations[recommendation_id] = patient_location
    
    def require(self, recommendation_id: str) -> Recommendation:
        """Return a recommendation or raise KeyError if not found."""
        if recommendation_id not in self._recommendations:
            raise KeyError(
                f"Unknown or expired recommendation_id: {recommendation_id}"
            )
        return self._recommendations[recommendation_id]
    
    def get_patient_location(
        self,
        recommendation_id: str,
    ) -> Optional[PatientLocation]:
        """Return the PatientLocation stored with this recommendation, or None."""
        return self._patient_locations.get(recommendation_id)
    
    def require_provider(
        self,
        recommendation_id: str,
        provider_id: str,
    ) -> ProviderCandidate:
        """Validate recommendation existence and provider membership."""
        recommendation = self.require(recommendation_id)
        
        for provider in recommendation.top_providers:
            if provider.provider_id == provider_id:
                return provider
        
        raise KeyError(
            f"Provider '{provider_id}' is not part of recommendation "
            f"'{recommendation_id}'"
        )


class MockAppointmentAgentClient:
    """Mock implementation of AppointmentAgentClient for testing.
    
    Provides get_availability(), book(), reschedule(), cancel_appointment()
    methods that return test data without making HTTP calls.
    """
    
    def __init__(self):
        self.get_availability = Mock()
        self.book = Mock()
        self.reschedule = Mock()
        self.cancel_appointment = Mock()


@pytest.fixture
def mock_recommendation_store():
    """Fixture providing a MockRecommendationStore instance."""
    return MockRecommendationStore()


@pytest.fixture
def mock_appointment_client():
    """Fixture providing a MockAppointmentAgentClient instance."""
    return MockAppointmentAgentClient()


@pytest.fixture
def sample_care_decision() -> CareDecision:
    """Sample CareDecision fixture for URGENT_CARE destination."""
    return CareDecision(
        rule_id="UC-001-INFECTION",
        priority=30,
        destination="URGENT_CARE",
        specialty=None,
        status="DOCUMENT_SUPPORTED",
        explanation="Same-day evaluation appropriate for minor infection.",
    )


@pytest.fixture
def sample_specialist_care_decision() -> CareDecision:
    """Sample CareDecision fixture for SPECIALIST destination."""
    return CareDecision(
        rule_id="SPEC-002-PULM",
        priority=50,
        destination="SPECIALIST",
        specialty="PULMONOLOGY",
        status="DOCUMENT_SUPPORTED",
        explanation="Specialist evaluation recommended for chronic respiratory condition.",
    )


@pytest.fixture
def sample_provider_candidates() -> List[ProviderCandidate]:
    """Sample ranked provider list fixture."""
    return [
        ProviderCandidate(
            provider_id="osm:node:1001",
            name="City Urgent Care",
            destination_type="URGENT_CARE",
            specialty=None,
            latitude=30.2701,
            longitude=-97.7448,
            address="123 Main St, Austin, TX 78701",
            distance_km=0.36,
            score=0.986,
            source="osm",
        ),
        ProviderCandidate(
            provider_id="osm:node:1002",
            name="Downtown Medical Center",
            destination_type="URGENT_CARE",
            specialty=None,
            latitude=30.2672,
            longitude=-97.7431,
            address="456 Oak Ave, Austin, TX 78702",
            distance_km=0.52,
            score=0.941,
            source="osm",
        ),
        ProviderCandidate(
            provider_id="osm:node:1003",
            name="Riverside Urgent Care",
            destination_type="URGENT_CARE",
            specialty=None,
            latitude=30.2500,
            longitude=-97.7500,
            address="789 River Rd, Austin, TX 78703",
            distance_km=1.24,
            score=0.823,
            source="osm",
        ),
    ]


@pytest.fixture
def sample_specialist_provider_candidates() -> List[ProviderCandidate]:
    """Sample ranked provider list for SPECIALIST destination."""
    return [
        ProviderCandidate(
            provider_id="osm:node:2001",
            name="Austin Pulmonary Specialists",
            destination_type="SPECIALIST",
            specialty="PULMONOLOGY",
            latitude=30.3000,
            longitude=-97.7500,
            address="100 Medical Pkwy, Austin, TX 78704",
            distance_km=2.15,
            score=0.925,
            source="osm",
        ),
        ProviderCandidate(
            provider_id="osm:node:2002",
            name="Central Texas Lung Clinic",
            destination_type="SPECIALIST",
            specialty="PULMONOLOGY",
            latitude=30.2800,
            longitude=-97.7400,
            address="200 Specialty Dr, Austin, TX 78705",
            distance_km=1.82,
            score=0.910,
            source="osm",
        ),
    ]


@pytest.fixture
def sample_recommendation(
    sample_care_decision,
    sample_provider_candidates,
) -> Recommendation:
    """Sample Recommendation fixture with URGENT_CARE decision and providers."""
    return Recommendation(
        recommendation_id="rec_test123456",
        decision=sample_care_decision,
        top_providers=sample_provider_candidates,
    )


@pytest.fixture
def sample_specialist_recommendation(
    sample_specialist_care_decision,
    sample_specialist_provider_candidates,
) -> Recommendation:
    """Sample Recommendation fixture with SPECIALIST decision and providers."""
    return Recommendation(
        recommendation_id="rec_spec_test789",
        decision=sample_specialist_care_decision,
        top_providers=sample_specialist_provider_candidates,
    )


@pytest.fixture
def sample_patient_location() -> PatientLocation:
    """Sample PatientLocation fixture for Austin, TX."""
    return PatientLocation(
        latitude=30.2672,
        longitude=-97.7431,
        radius_km=15.0,
        address="Austin, TX 78701",
    )


@pytest.fixture
def sample_appointment_slots() -> List[AppointmentSlot]:
    """Sample appointment slots fixture for availability testing."""
    return [
        AppointmentSlot(
            slot_id="slot_001",
            provider_id="osm:node:1001",
            start_time="2026-08-25T09:00:00Z",
            end_time="2026-08-25T09:30:00Z",
        ),
        AppointmentSlot(
            slot_id="slot_002",
            provider_id="osm:node:1001",
            start_time="2026-08-25T10:00:00Z",
            end_time="2026-08-25T10:30:00Z",
        ),
        AppointmentSlot(
            slot_id="slot_003",
            provider_id="osm:node:1001",
            start_time="2026-08-25T14:00:00Z",
            end_time="2026-08-25T14:30:00Z",
        ),
    ]


@pytest.fixture
def sample_booking_confirmation(
    sample_appointment_slots,
) -> AppointmentConfirmation:
    """Sample booking confirmation fixture."""
    from models.schemas import BookingConfirmation
    
    return BookingConfirmation(
        appointment_id="appt_abc123",
        status="BOOKED",
        provider_id="osm:node:1001",
        slot=sample_appointment_slots[0],
    )


@pytest.fixture
def sample_appointment_confirmation(
    sample_appointment_slots,
) -> AppointmentConfirmation:
    """Sample appointment confirmation fixture (richer format)."""
    return AppointmentConfirmation(
        appointment_id="appt_abc123",
        patient_id="patient_12345",
        status="BOOKED",
        provider_id="osm:node:1001",
        provider_name="City Urgent Care",
        care_type="URGENT_CARE",
        specialty=None,
        hospital_id=None,
        hospital_name=None,
        slot=sample_appointment_slots[0],
        date="2026-08-25",
        time="09:00",
    )


@pytest.fixture
def sample_cancellation_status() -> AppointmentStatusResponse:
    """Sample cancellation status response fixture."""
    return AppointmentStatusResponse(
        appointment_id="appt_abc123",
        patient_id="patient_12345",
        status="CANCELLED",
        provider_id="osm:node:1001",
        provider_name="City Urgent Care",
        care_type="URGENT_CARE",
        slot=None,
    )


# ---------------------------------------------------------------------------
# Unit tests will be added in subsequent tasks (8.2-8.6)
# ---------------------------------------------------------------------------

class TestFixturesLoading:
    """Verify that all fixtures can be loaded successfully."""
    
    def test_mock_recommendation_store_fixture(self, mock_recommendation_store):
        """MockRecommendationStore fixture loads without error."""
        assert isinstance(mock_recommendation_store, MockRecommendationStore)
    
    def test_mock_appointment_client_fixture(self, mock_appointment_client):
        """MockAppointmentAgentClient fixture loads without error."""
        assert isinstance(mock_appointment_client, MockAppointmentAgentClient)
    
    def test_sample_care_decision_fixture(self, sample_care_decision):
        """Sample CareDecision fixture loads with correct destination."""
        assert sample_care_decision.destination == "URGENT_CARE"
        assert sample_care_decision.specialty is None
    
    def test_sample_specialist_care_decision_fixture(
        self,
        sample_specialist_care_decision,
    ):
        """Sample specialist CareDecision fixture loads with specialty."""
        assert sample_specialist_care_decision.destination == "SPECIALIST"
        assert sample_specialist_care_decision.specialty == "PULMONOLOGY"
    
    def test_sample_provider_candidates_fixture(
        self,
        sample_provider_candidates,
    ):
        """Sample provider candidates fixture loads with correct count."""
        assert len(sample_provider_candidates) == 3
        assert sample_provider_candidates[0].provider_id == "osm:node:1001"
        assert sample_provider_candidates[0].destination_type == "URGENT_CARE"
    
    def test_sample_specialist_provider_candidates_fixture(
        self,
        sample_specialist_provider_candidates,
    ):
        """Sample specialist provider candidates fixture loads correctly."""
        assert len(sample_specialist_provider_candidates) == 2
        assert sample_specialist_provider_candidates[0].specialty == "PULMONOLOGY"
    
    def test_sample_recommendation_fixture(self, sample_recommendation):
        """Sample Recommendation fixture loads with decision and providers."""
        assert sample_recommendation.recommendation_id == "rec_test123456"
        assert sample_recommendation.decision.destination == "URGENT_CARE"
        assert len(sample_recommendation.top_providers) == 3
    
    def test_sample_specialist_recommendation_fixture(
        self,
        sample_specialist_recommendation,
    ):
        """Sample specialist Recommendation fixture loads correctly."""
        assert sample_specialist_recommendation.recommendation_id == "rec_spec_test789"
        assert sample_specialist_recommendation.decision.destination == "SPECIALIST"
        assert len(sample_specialist_recommendation.top_providers) == 2
    
    def test_sample_patient_location_fixture(self, sample_patient_location):
        """Sample PatientLocation fixture loads with coordinates."""
        assert sample_patient_location.latitude == 30.2672
        assert sample_patient_location.longitude == -97.7431
        assert sample_patient_location.address == "Austin, TX 78701"
    
    def test_sample_appointment_slots_fixture(self, sample_appointment_slots):
        """Sample appointment slots fixture loads with correct count."""
        assert len(sample_appointment_slots) == 3
        assert sample_appointment_slots[0].slot_id == "slot_001"
        assert sample_appointment_slots[0].provider_id == "osm:node:1001"
    
    def test_sample_booking_confirmation_fixture(
        self,
        sample_booking_confirmation,
    ):
        """Sample booking confirmation fixture loads correctly."""
        assert sample_booking_confirmation.appointment_id == "appt_abc123"
        assert sample_booking_confirmation.status == "BOOKED"
    
    def test_sample_appointment_confirmation_fixture(
        self,
        sample_appointment_confirmation,
    ):
        """Sample appointment confirmation fixture loads correctly."""
        assert sample_appointment_confirmation.appointment_id == "appt_abc123"
        assert sample_appointment_confirmation.patient_id == "patient_12345"
        assert sample_appointment_confirmation.status == "BOOKED"
        assert sample_appointment_confirmation.care_type == "URGENT_CARE"
    
    def test_sample_cancellation_status_fixture(
        self,
        sample_cancellation_status,
    ):
        """Sample cancellation status fixture loads correctly."""
        assert sample_cancellation_status.appointment_id == "appt_abc123"
        assert sample_cancellation_status.status == "CANCELLED"


class TestMockRecommendationStore:
    """Test MockRecommendationStore behavior."""
    
    def test_require_raises_key_error_for_unknown_id(
        self,
        mock_recommendation_store,
    ):
        """MockRecommendationStore.require raises KeyError for unknown ID."""
        with pytest.raises(KeyError, match="Unknown or expired recommendation_id"):
            mock_recommendation_store.require("unknown_id")
    
    def test_add_and_require_recommendation(
        self,
        mock_recommendation_store,
        sample_recommendation,
    ):
        """MockRecommendationStore can store and retrieve recommendations."""
        mock_recommendation_store.add_recommendation(
            "rec_test123456",
            sample_recommendation,
        )
        
        retrieved = mock_recommendation_store.require("rec_test123456")
        assert retrieved.recommendation_id == "rec_test123456"
        assert retrieved.decision.destination == "URGENT_CARE"
    
    def test_require_provider_returns_correct_provider(
        self,
        mock_recommendation_store,
        sample_recommendation,
    ):
        """MockRecommendationStore.require_provider returns matching provider."""
        mock_recommendation_store.add_recommendation(
            "rec_test123456",
            sample_recommendation,
        )
        
        provider = mock_recommendation_store.require_provider(
            "rec_test123456",
            "osm:node:1001",
        )
        assert provider.provider_id == "osm:node:1001"
        assert provider.name == "City Urgent Care"
    
    def test_require_provider_raises_for_unknown_provider(
        self,
        mock_recommendation_store,
        sample_recommendation,
    ):
        """MockRecommendationStore.require_provider raises KeyError for unknown provider."""
        mock_recommendation_store.add_recommendation(
            "rec_test123456",
            sample_recommendation,
        )
        
        with pytest.raises(KeyError, match="Provider .* is not part of recommendation"):
            mock_recommendation_store.require_provider(
                "rec_test123456",
                "osm:node:9999",
            )
    
    def test_get_patient_location_returns_none_for_unknown_id(
        self,
        mock_recommendation_store,
    ):
        """MockRecommendationStore.get_patient_location returns None for unknown ID."""
        location = mock_recommendation_store.get_patient_location("unknown_id")
        assert location is None
    
    def test_add_and_get_patient_location(
        self,
        mock_recommendation_store,
        sample_recommendation,
        sample_patient_location,
    ):
        """MockRecommendationStore can store and retrieve patient location."""
        mock_recommendation_store.add_recommendation(
            "rec_test123456",
            sample_recommendation,
            patient_location=sample_patient_location,
        )
        
        retrieved = mock_recommendation_store.get_patient_location("rec_test123456")
        assert retrieved is not None
        assert retrieved.latitude == 30.2672
        assert retrieved.longitude == -97.7431


class TestMockAppointmentAgentClient:
    """Test MockAppointmentAgentClient behavior."""
    
    def test_get_availability_is_mockable(
        self,
        mock_appointment_client,
        sample_appointment_slots,
    ):
        """MockAppointmentAgentClient.get_availability can be mocked."""
        mock_appointment_client.get_availability.return_value = sample_appointment_slots
        
        result = mock_appointment_client.get_availability(
            provider_id="osm:node:1001",
            care_type="URGENT_CARE",
            specialty=None,
        )
        
        assert len(result) == 3
        assert result[0].slot_id == "slot_001"
    
    def test_book_is_mockable(
        self,
        mock_appointment_client,
        sample_booking_confirmation,
    ):
        """MockAppointmentAgentClient.book can be mocked."""
        mock_appointment_client.book.return_value = sample_booking_confirmation
        
        from models.schemas import BookingRequest
        
        request = BookingRequest(
            patient_id="patient_12345",
            recommendation_id="rec_test123456",
            provider_id="osm:node:1001",
            slot_id="slot_001",
        )
        
        result = mock_appointment_client.book(request=request, specialty=None)
        
        assert result.appointment_id == "appt_abc123"
        assert result.status == "BOOKED"
    
    def test_reschedule_is_mockable(
        self,
        mock_appointment_client,
        sample_appointment_confirmation,
    ):
        """MockAppointmentAgentClient.reschedule can be mocked."""
        rescheduled = AppointmentConfirmation(
            appointment_id=sample_appointment_confirmation.appointment_id,
            patient_id=sample_appointment_confirmation.patient_id,
            status="RESCHEDULED",
            provider_id=sample_appointment_confirmation.provider_id,
            provider_name=sample_appointment_confirmation.provider_name,
            care_type=sample_appointment_confirmation.care_type,
            specialty=sample_appointment_confirmation.specialty,
            hospital_id=sample_appointment_confirmation.hospital_id,
            hospital_name=sample_appointment_confirmation.hospital_name,
            slot=sample_appointment_confirmation.slot,
            date=sample_appointment_confirmation.date,
            time=sample_appointment_confirmation.time,
        )
        mock_appointment_client.reschedule.return_value = rescheduled
        
        from appointment.schemas import RescheduleRequest
        
        request = RescheduleRequest(
            patient_id="patient_12345",
            appointment_id="appt_abc123",
            new_slot_id="slot_002",
        )
        
        result = mock_appointment_client.reschedule(request)
        
        assert result.appointment_id == "appt_abc123"
        assert result.status == "RESCHEDULED"
    
    def test_cancel_appointment_is_mockable(
        self,
        mock_appointment_client,
        sample_cancellation_status,
    ):
        """MockAppointmentAgentClient.cancel_appointment can be mocked."""
        mock_appointment_client.cancel_appointment.return_value = (
            sample_cancellation_status
        )
        
        from appointment.schemas import CancellationRequest
        
        request = CancellationRequest(
            patient_id="patient_12345",
            appointment_id="appt_abc123",
        )
        
        result = mock_appointment_client.cancel_appointment(request)
        
        assert result.appointment_id == "appt_abc123"
        assert result.status == "CANCELLED"
