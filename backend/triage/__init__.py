"""triage — multi-agent bug-report triage on LlamaIndex AgentWorkflow.

Raw feedback (store reviews, Discord, support email) goes in; de-duplicated,
severity-rated engineering tickets come out. Four agents hand work to each
other, share state through the workflow Context, and pause for a human before
anything high-severity is written.

Reading order:

    settings.py      -> local models (Ollama), paths, thresholds
    schemas.py       -> the Pydantic records agents produce (Intake, Investigation, Triage)
    state.py         -> helpers for the shared workflow state
    tools/           -> plain functions the agents call; each `record_*` tool
                        validates + stores a schema and tells the model what to do next
    agents.py        -> the four FunctionAgents and the AgentWorkflow wiring
    runner.py        -> run one item, stream events, handle the human gate
    cli.py           -> `triage run | eval | inbox`
"""
