# XBrainLab Future Architecture (Conceptual)

This document outlines the **Prompt Assembly Architecture** of the XBrainLab Agent System. It emphasizes how the system dynamically constructs the AI's cognitive context by assembling four key components before invoking the LLM.

## Conceptual Framework: The Prompt Assembler

The core mechanism is a **Dynamic Prompt Assembler** that gathers the necessary context into a comprehensive "Instruction Box" for the Agent.

```mermaid
graph TD
    %% Input
    User(["User Command"]) --> Assembler{"<b>Context Assembler</b>"}

    %% Four Core Components
    subgraph Components [Cognitive Resources]
        direction TB
        P1["<b>1. System Prompt</b><br/>Defines Agent Role & Logic<br/>(ReAct Pattern)"]

        P2["<b>2. Tool Definitions</b><br/><i>Stateless Full Insertion</i><br/>(Dynamic Action Space determined by Backend)"]

        P3["<b>3. RAG Context</b><br/>Retrieved from Qdrant Vector DB<br/>(Domain Expertise)"]

        P4["<b>4. Memory</b><br/>Conversation History<br/>(Short-term Context)"]
    end

    %% Assembly Flow
    P1 --> Assembler
    P2 --> Assembler
    P3 --> Assembler
    P4 --> Assembler

    %% Decision & Verification Flow
    Assembler -->|"Complete Instruction Prompt"| LLM["LLM Agent"]

    LLM -->|"Proposed Tool Call"| Verifier{"<b>Verification Layer</b><br/>(Script & Confidence Check)"}

    Verifier -->|"High Confidence & Valid"| Backend["<b>Backend System</b><br/>(Execution & State Management)"]

    Verifier -->|"Low Confidence / Invalid"| Reflection["<b>Self-Correction</b><br/>(Reflect on Error)"]

    Reflection -.->|"Re-Examine Intent"| Assembler

    %% State Feedback
    Backend -.->|"State Update"| P1
    Backend -.->|"State Update / Filter"| P2

    class Assembler,LLM main;
    class P1,P2,P3,P4,Components resource;
    class Backend output;
    class Verifier,Reflection safety;

    classDef safety fill:#ffebee,stroke:#c62828,stroke-width:2px;
```

## Key Mechanisms

### 1. Dynamic Tool Definition (Component 2)
Crucially, the **Tool Definitions** are not retrieved via semantic search but are **inserted in full** based on the current system state.
- **State-Driven**: The backend determines which tools are valid (e.g., "Filter Data" is only included if data is loaded).
- **Full Context**: The Agent sees the exact schema for all available tools, ensuring precise execution without hallucination.

### 2. Context Retrieval (Component 3)
Domain-specific knowledge is retrieved from the **Qdrant Vector Database** (RAG) to ground the Agent's reasoning in scientific facts and best practices.

### 3. The Verification Layer (Safety & Correction)
Before execution, every proposed Tool Call undergoes a strictly defined check:
- **Script Validation**: A deterministic script checks if the call is syntactically valid and logically sound (e.g., parameter range checks).
- **Confidence Check**: The system evaluates the LLM's confidence.
  - **Low Confidence / Script Fail** → Triggers **Self-Correction** (Reflection), sending the error back to the Assembler to retry.
  - **High Confidence & Valid** → Proceeds to the **Backend System** for execution.

### 4. The Assembler
The Assembler acts as the cognitive integration layer, fusing the User's intent with the System Prompt, Tool Logic, RAG Knowledge, Memory, and any **Feedback from Verification** into a single, coherent prompt.
