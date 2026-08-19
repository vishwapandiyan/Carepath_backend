from typing import Any
from pydantic import BaseModel, Field


class CarePlanTask(BaseModel):
    task: str
    status: str = Field(description="pending | completed")


class CarePlanAgentStatus(BaseModel):
    tasks: list[CarePlanTask] = Field(default_factory=list)
    status: str = Field(default="on_track", description="on_track | at_risk | completed")


class FollowUpAgentStatus(BaseModel):
    last_checkin: str | None = None
    next_checkin: str | None = None
    is_scheduled: bool = False


class ResponseAnalyserAgentStatus(BaseModel):
    key_info: dict[str, Any] = Field(default_factory=dict)


class AppointmentAgentStatus(BaseModel):
    is_appointment: bool = False
    date: str | None = None


class PostDischargeStatusOut(BaseModel):
    patient_id: str
    care_plan: CarePlanAgentStatus
    follow_up: FollowUpAgentStatus
    response_analyser: ResponseAnalyserAgentStatus
    appointment: AppointmentAgentStatus
