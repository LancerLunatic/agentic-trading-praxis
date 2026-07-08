import os
from langchain_core.tracers.base import BaseTracer
from langchain_core.tracers.schemas import Run
from langsmith import Client
from core.logger import get_logger

logger = get_logger("telemetry")

class ConditionalTracer(BaseTracer):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Check tracing environment toggles
        self.tracing_enabled = os.environ.get("LANGCHAIN_TRACING_V2", "false").lower() == "true"
        self.api_key_present = bool(os.environ.get("LANGSMITH_API_KEY"))
        if self.tracing_enabled and self.api_key_present:
            self.client = Client()
        else:
            self.client = None
        self.root_run = None

    def _persist_run(self, run: Run) -> None:
        # Process only the root run when the entire graph execution completes
        if run.parent_run_id is None:
            self.root_run = run
            self._process_completed_run(run)

    def _process_completed_run(self, run: Run) -> None:
        # Check if the global tracing toggle is enabled
        if not (self.tracing_enabled and self.api_key_present):
            self._log_run_locally(run, reason="Tracing toggle disabled or LANGSMITH_API_KEY missing")
            return

        # Check conditions to decide if we should export to LangSmith
        export_to_langsmith = self._should_export_to_langsmith(run)

        if export_to_langsmith:
            self._export_to_langsmith(run)
        else:
            self._log_run_locally(run, reason="Normal execution (trace sampling filtered)")

    def _should_export_to_langsmith(self, run: Run) -> bool:
        # Check if there's an active GraphInterrupt exception
        if self._has_interrupt_error(run):
            return True

        # Check if any run in the execution tree had an anomaly or loop failure
        return self._has_anomaly_or_loop_failure(run)

    def _has_anomaly_or_loop_failure(self, run: Run) -> bool:
        outputs = run.outputs or {}
        # Handle list outputs if stream/astream was used
        if isinstance(outputs, list) and len(outputs) > 0:
            outputs = outputs[-1] if isinstance(outputs[-1], dict) else {}
        
        if isinstance(outputs, dict):
            # Check loop_failed or reflection_count limit reached
            if outputs.get("loop_failed", False):
                return True
            
            # Check reflection_count >= 3
            reflection_count = outputs.get("reflection_count", 0)
            if reflection_count >= 3:
                return True

            # Check if confidence_score is low (anomaly detected)
            confidence_score = outputs.get("confidence_score")
            if confidence_score is not None and float(confidence_score) < 0.70:
                return True

            # Check if evaluator critique indicates an anomaly
            evaluation_critique = outputs.get("evaluation_critique", "")
            if "anomaly" in evaluation_critique.lower() or "error" in evaluation_critique.lower():
                return True

        # Check child runs recursively
        if run.child_runs:
            for child in run.child_runs:
                if self._has_anomaly_or_loop_failure(child):
                    return True
                    
        return False

    def _has_interrupt_error(self, run: Run) -> bool:
        if run.error and ("GraphInterrupt" in run.error or "interrupt" in run.error.lower()):
            return True
        if run.child_runs:
            for child in run.child_runs:
                if self._has_interrupt_error(child):
                    return True
        return False

    def _export_to_langsmith(self, run: Run) -> None:
        try:
            if self.client:
                project_name = os.environ.get("LANGSMITH_PROJECT", "default")
                self._upload_run_tree(run, project_name=project_name)
                logger.info("Successfully exported telemetry to LangSmith", run_id=str(run.id))
            else:
                logger.warning("LangSmith client not initialized, skipping export", run_id=str(run.id))
        except Exception as e:
            logger.error("Failed to export telemetry to LangSmith", error=str(e), run_id=str(run.id))

    def _upload_run_tree(self, run: Run, parent_run_id=None, project_name="default") -> None:
        # Upload using the LangSmith Client
        self.client.create_run(
            id=run.id,
            name=run.name,
            run_type=run.run_type,
            inputs=run.inputs or {},
            outputs=run.outputs or {},
            error=run.error,
            start_time=run.start_time,
            end_time=run.end_time,
            parent_run_id=parent_run_id or run.parent_run_id,
            extra=run.extra or {},
            tags=run.tags or [],
            events=run.events or [],
            project_name=project_name
        )
        if run.child_runs:
            for child in run.child_runs:
                self._upload_run_tree(child, parent_run_id=run.id, project_name=project_name)

    def _log_run_locally(self, run: Run, reason: str) -> None:
        outputs = run.outputs or {}
        if isinstance(outputs, list) and len(outputs) > 0:
            outputs = outputs[-1] if isinstance(outputs[-1], dict) else {}
        elif not isinstance(outputs, dict):
            outputs = {}
            
        duration_seconds = (run.end_time - run.start_time).total_seconds() if run.end_time and run.start_time else None
        
        state_summary = {
            "run_id": str(run.id),
            "name": run.name,
            "inputs": run.inputs or {},
            "outputs": outputs,
            "error": run.error,
            "duration_seconds": duration_seconds,
            "reason": reason,
            "final_decision": outputs.get("signal", "UNKNOWN")
        }
        logger.info("Local telemetry log (not exported to LangSmith)", **state_summary)

def patch_app_with_telemetry(compiled_graph):
    """
    Patches CompiledStateGraph execution methods to inject the ConditionalTracer.
    """
    orig_invoke = compiled_graph.invoke
    orig_ainvoke = compiled_graph.ainvoke
    orig_stream = compiled_graph.stream
    orig_astream = compiled_graph.astream

    def _inject_callback(config):
        config = config or {}
        callbacks = config.get("callbacks") or []
        if not any(isinstance(cb, ConditionalTracer) for cb in callbacks):
            config["callbacks"] = list(callbacks) + [ConditionalTracer()]
        return config

    def new_invoke(input, config=None, **kwargs):
        config = _inject_callback(config)
        return orig_invoke(input, config=config, **kwargs)

    async def new_ainvoke(input, config=None, **kwargs):
        config = _inject_callback(config)
        return await orig_ainvoke(input, config=config, **kwargs)

    def new_stream(input, config=None, **kwargs):
        config = _inject_callback(config)
        return orig_stream(input, config=config, **kwargs)

    async def new_astream(input, config=None, **kwargs):
        config = _inject_callback(config)
        async for chunk in orig_astream(input, config=config, **kwargs):
            yield chunk

    compiled_graph.invoke = new_invoke
    compiled_graph.ainvoke = new_ainvoke
    compiled_graph.stream = new_stream
    compiled_graph.astream = new_astream

    return compiled_graph
