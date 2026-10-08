# Five-minute demo

1. Start `uvicorn superagent.api:app --reload` and open `http://localhost:8000`.
2. Submit: `Analyze telecom incident logs and propose a remediation change`.
3. Watch the timeline stop at `waiting_approval`; inspect the stored plan and trace.
4. Approve as reviewer `demo-operator`; verify execution resumes rather than restarting.
5. Submit refinery and legal tasks to show skill isolation.
6. Restart the server during a queued task and show checkpoint recovery.

The offline provider is deterministic and requires no credentials. No tool connects to a real operational system.

