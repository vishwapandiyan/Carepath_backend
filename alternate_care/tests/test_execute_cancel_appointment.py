"""
Unit tests for execute_cancel_appointment tool executor.
"""

from unittest.mock import MagicMock, patch
import pytest

from app.services.alternate_care.agents.tools.navigation_tools import execute_cancel_appointment
from app.services.alternate_care.appointment.schemas import AppointmentStatusResponse


class TestExecuteCancelAppointment:
    """Tests for execute_cancel_appointment executor function."""

    def test_cancel_appointment_success(self):
        """Valid parameters should return success envelope."""
        # Mock the AppointmentAgentClient
        mock_status = AppointmentStatusResponse(
            appointment_id="APT-001",
            patient_id="P-12345",
            status="CANCELLED",
        )
        
        with patch("agents.tools.navigation_tools.AppointmentAgentClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.cancel_appointment.return_value = mock_status
            mock_client_class.return_value = mock_client
            
            result = execute_cancel_appointment(
                patient_id="P-12345",
                appointment_id="APT-001",
            )
        
        assert result["ok"] is True
        assert result["appointment_id"] == "APT-001"
        assert result["status"] == "CANCELLED"
        assert result["patient_id"] == "P-12345"
        
        # Verify the client was called correctly
        mock_client.cancel_appointment.assert_called_once()
        call_args = mock_client.cancel_appointment.call_args[0][0]
        assert call_args.patient_id == "P-12345"
        assert call_args.appointment_id == "APT-001"

    def test_cancel_appointment_http_error(self):
        """HTTP error from AppointmentAgentClient should return error envelope."""
        import requests
        
        # Create a mock response with status code
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        http_error = requests.HTTPError()
        http_error.response = mock_response
        
        with patch("agents.tools.navigation_tools.AppointmentAgentClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.cancel_appointment.side_effect = http_error
            mock_client_class.return_value = mock_client
            
            result = execute_cancel_appointment(
                patient_id="P-12345",
                appointment_id="APT-001",
            )
        
        assert result["ok"] is False
        assert "Cancellation failed: 404" in result["error"]

    def test_cancel_appointment_unexpected_error(self):
        """Unexpected exceptions should return error envelope."""
        with patch("agents.tools.navigation_tools.AppointmentAgentClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.cancel_appointment.side_effect = Exception("Network timeout")
            mock_client_class.return_value = mock_client
            
            result = execute_cancel_appointment(
                patient_id="P-12345",
                appointment_id="APT-001",
            )
        
        assert result["ok"] is False
        assert "Network timeout" in result["error"]

    def test_cancel_appointment_logs_operations(self):
        """Should log operations at INFO level."""
        mock_status = AppointmentStatusResponse(
            appointment_id="APT-001",
            patient_id="P-12345",
            status="CANCELLED",
        )
        
        with patch("agents.tools.navigation_tools.AppointmentAgentClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.cancel_appointment.return_value = mock_status
            mock_client_class.return_value = mock_client
            
            with patch("agents.tools.navigation_tools.logger") as mock_logger:
                execute_cancel_appointment(
                    patient_id="P-12345",
                    appointment_id="APT-001",
                )
                
                # Verify logging occurred
                assert mock_logger.info.call_count == 2
                # First log: starting operation
                first_call = mock_logger.info.call_args_list[0][0][0]
                assert "cancel_appointment:" in first_call
                assert "patient_id" in first_call
                
                # Second log: success
                second_call = mock_logger.info.call_args_list[1][0][0]
                assert "success" in second_call
