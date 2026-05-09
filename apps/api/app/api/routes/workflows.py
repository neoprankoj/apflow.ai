from fastapi import APIRouter, Depends

from app.agents.orchestration.ap_workflow_orchestrator_agent import APWorkflowOrchestratorAgent
from app.api.dependencies import get_orchestrator_agent
from app.core.schemas import OrchestratorOutput, WorkflowEventInput

router = APIRouter()


@router.post("/events", response_model=OrchestratorOutput)
def accept_workflow_event(
    event: WorkflowEventInput,
    orchestrator: APWorkflowOrchestratorAgent = Depends(get_orchestrator_agent),
) -> OrchestratorOutput:
    return orchestrator.handle_event(event)
