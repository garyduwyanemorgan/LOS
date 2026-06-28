"""Exception hierarchy for the Lagoons Operating System."""

from backend.core.exceptions.exceptions import (
    AuthenticationException,
    AuthorizationException,
    DatabaseException,
    DecisionEngineException,
    EventBusException,
    LOSException,
    ResourceNotFoundException,
    ScientificModelException,
    ScientificServiceException,
    SharedMemoryException,
    SimulationException,
    SRGException,
    ValidationException,
)

__all__ = [
    "AuthenticationException",
    "AuthorizationException",
    "DatabaseException",
    "DecisionEngineException",
    "EventBusException",
    "LOSException",
    "ResourceNotFoundException",
    "SRGException",
    "ScientificModelException",
    "ScientificServiceException",
    "SharedMemoryException",
    "SimulationException",
    "ValidationException",
]
