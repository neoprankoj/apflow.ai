from app.agents.base import BaseAgent
from app.core.schemas import MetricEventInput, MetricEventOutput, StoredMetricEvent


class MonitoringAgent(BaseAgent[MetricEventInput, MetricEventOutput]):
    name = "MonitoringAgent"
    responsibility = "Track service health, queues, latency, failures, and agent metrics."

    def __init__(self, alert_thresholds: dict[str, float] | None = None) -> None:
        self.alert_thresholds = alert_thresholds or {
            "agent.failure": 1,
            "queue.depth": 100,
            "ocr.low_confidence_rate": 0.2,
            "erp.sync_failure": 1,
        }
        self._metrics: list[StoredMetricEvent] = []

    def record_metric(self, metric: MetricEventInput) -> MetricEventOutput:
        alerts = self._alerts_for(metric)
        stored = StoredMetricEvent(**metric.model_dump(), alerts=alerts)
        self._metrics.append(stored)
        return MetricEventOutput(
            metric_id=stored.metric_id,
            status="alert_triggered" if alerts else "recorded",
            alerts=alerts,
        )

    @property
    def metrics(self) -> tuple[StoredMetricEvent, ...]:
        return tuple(self._metrics)

    def _alerts_for(self, metric: MetricEventInput) -> list[str]:
        threshold = self.alert_thresholds.get(metric.metric_event)
        if threshold is None or metric.value < threshold:
            return []
        return [f"{metric.metric_event} reached {metric.value}, threshold {threshold}"]
