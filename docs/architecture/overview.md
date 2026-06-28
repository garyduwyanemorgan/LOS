# LOS Architecture Overview

## Loop of Loops

The Lagoons Operating System is built on a Loop of Loops architecture.
Five independent scientific loops operate continuously, each representing a complete scientific discipline.

```
                        ┌─────────────────────────────────────────┐
                        │           EVENT BUS (Redis Streams)       │
                        │                                           │
┌──────────────────┐    │  ┌─────────┐    ┌─────────┐    ┌──────┐ │
│  HYDROLOGICAL    │◄───┼──┤  HIGH   │    │ MEDIUM  │    │  LOW │ │
│  LOOP            │───►┼──┤ STREAM  │    │ STREAM  │    │STREAM│ │
│                  │    │  └─────────┘    └─────────┘    └──────┘ │
│ • Water balance  │    │                                          │
│ • Residence time │    └──────────────────────────────────────────┘
│ • Darcy flux     │              │                │
│ • ET₀ (FAO-56)   │              ▼                ▼
└──────────────────┘    ┌─────────────┐   ┌──────────────────────┐
                        │  SHARED     │   │  SCIENTIFIC           │
┌──────────────────┐    │  MEMORY     │   │  RELATIONSHIP GRAPH   │
│  CHEMICAL        │    │             │   │  (Neo4j)              │
│  LOOP            │    │  Redis:     │   │                       │
│                  │    │  • Working  │   │  Cause → Effect       │
│ • DO saturation  │    │  • Short    │   │  relationships with   │
│ • Redox (ORP)    │    │  • Science  │   │  confidence scores    │
│ • Nutrient cycle │    │             │   │  updated by learning  │
│ • Trophic state  │    │  PostgreSQL:│   │                       │
└──────────────────┘    │  • Long-term│   └──────────────────────┘
                        │  • Learning │              │
┌──────────────────┐    └─────────────┘              │
│  ECOLOGICAL      │              │                  │
│  LOOP            │              ▼                  ▼
│                  │    ┌────────────────────────────────────────┐
│ • Bloom risk     │    │            DECISION ENGINE              │
│ • Algal dynamics │    │                                        │
│ • Cyanobacteria  │    │  1. Assemble system state              │
│ • Succession     │    │  2. Query SRG for hypotheses           │
└──────────────────┘    │  3. Generate 8 candidate actions       │
                        │  4. Score against 7 objectives         │
┌──────────────────┐    │  5. Rank by weighted total score       │
│  INFRASTRUCTURE  │    │  6. Generate explainable recommendation│
│  LOOP            │    └────────────────────────────────────────┘
│                  │                       │
│ • Aerator status │                       ▼
│ • Pump health    │    ┌────────────────────────────────────────┐
│ • Sensor cover   │    │          AI ORCHESTRATOR               │
│ • Maintenance    │    │          (LangGraph + Claude claude-sonnet-4-6)  │
└──────────────────┘    │                                        │
                        │  Generates explainable narrative.      │
                        │  Scientific models remain authoritative.│
                        └────────────────────────────────────────┘
```

## Key Principles

**Scientific Independence**: Each loop computes independently. The AI never modifies scientific models.

**Event-Driven**: All inter-service communication is via Events published to Redis Streams. No direct service coupling.

**Shared Memory**: Two-tier memory — Redis for working memory (< 6h TTL), PostgreSQL for long-term learning.

**Explainability**: Every recommendation must answer: What? Why? Which loops? What evidence? What confidence?

**Continuous Learning**: Every intervention is an experiment. Outcomes update SRG confidence and shared memory.

## Seven Operating Objectives

| # | Objective | Typical Weight |
|---|-----------|---------------|
| 1 | Protect the Lagoon | 20% |
| 2 | Water Quality | 20% |
| 3 | Ecological Stability | 20% |
| 4 | Operational Cost | 10% |
| 5 | Regulatory Compliance | 15% |
| 6 | Scientific Confidence | 5% |
| 7 | Continuous Improvement | 10% |

Weights are configurable per-lagoon. Recommendations adapt without changing scientific models.

## Data Flow

```
Sensor Data
    │
    ▼
Observation Service → Event Bus → Scientific Loops
                                       │
                              Shared Memory ◄─── Hydrological State
                              Shared Memory ◄─── Chemical State
                              Shared Memory ◄─── Ecological State
                              Shared Memory ◄─── Infrastructure State
                                       │
                                       ▼
                              Decision Engine
                                       │
                                       ▼
                              RankedRecommendation
                                       │
                              ┌────────┴────────┐
                              │                 │
                           Approved          Rejected
                              │                 │
                         Intervention       (Learning)
                              │
                         Measurement
                              │
                        Learning Service
                              │
                     ┌────────┴────────┐
                     │                 │
                  Update SRG     Update Memory
```
