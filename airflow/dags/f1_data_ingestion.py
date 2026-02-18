"""
F1 Data Ingestion DAG with Operational Guarantees

Features:
- Task-level failure isolation
- Comprehensive logging and metrics
- Cost tracking and budget controls
- Retry logic with exponential backoff
- SLA monitoring and alerting
- Operational observability
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.task_group import TaskGroup
from airflow.exceptions import AirflowException
from prometheus_client import Counter, Histogram, Gauge

# Import custom modules
import sys
sys.path.insert(0, '/opt/airflow/src')

from ingestion.ergast_client import ErgastClient
from ingestion.fastf1_client import FastF1Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
DAG_RUN_DURATION = Histogram(
    'f1_dag_run_duration_seconds',
    'DAG run duration in seconds',
    ['dag_id', 'status']
)
TASK_DURATION = Histogram(
    'f1_task_duration_seconds',
    'Task execution duration',
    ['dag_id', 'task_id', 'status']
)
TASK_RETRY_COUNT = Counter(
    'f1_task_retries_total',
    'Total task retries',
    ['dag_id', 'task_id']
)
DATA_RECORDS_INGESTED = Counter(
    'f1_data_records_ingested_total',
    'Total data records ingested',
    ['data_source', 'data_type']
)
DAG_COST = Gauge(
    'f1_dag_cost_usd',
    'Estimated DAG run cost in USD',
    ['dag_id']
)

# Cost tracking (simplified estimates)
COST_PER_TASK_RUN = 0.01  # $0.01 per task execution
COST_PER_GB_DATA = 0.05   # $0.05 per GB processed
MONTHLY_BUDGET_USD = 200.0


class OperationalMetrics:
    """Track operational metrics for DAG runs"""

    def __init__(self, dag_id: str, run_id: str):
        self.dag_id = dag_id
        self.run_id = run_id
        self.start_time = datetime.now()
        self.task_metrics = {}
        self.total_cost = 0.0
        self.records_processed = 0

    def record_task_start(self, task_id: str):
        """Record task start time"""
        self.task_metrics[task_id] = {
            'start_time': datetime.now(),
            'status': 'running'
        }
        logger.info(f"[{self.dag_id}] Task {task_id} started")

    def record_task_end(self, task_id: str, status: str, records: int = 0):
        """Record task completion"""
        if task_id not in self.task_metrics:
            return

        end_time = datetime.now()
        duration = (end_time - self.task_metrics[task_id]['start_time']).total_seconds()

        self.task_metrics[task_id].update({
            'end_time': end_time,
            'duration': duration,
            'status': status,
            'records': records
        })

        # Update Prometheus metrics
        TASK_DURATION.labels(
            dag_id=self.dag_id,
            task_id=task_id,
            status=status
        ).observe(duration)

        # Update cost
        task_cost = COST_PER_TASK_RUN
        self.total_cost += task_cost
        DAG_COST.labels(dag_id=self.dag_id).set(self.total_cost)

        # Update records
        self.records_processed += records

        logger.info(
            f"[{self.dag_id}] Task {task_id} {status} - "
            f"Duration: {duration:.2f}s, Records: {records}, Cost: ${task_cost:.4f}"
        )

    def check_budget(self) -> bool:
        """Check if budget threshold exceeded"""
        if self.total_cost > (MONTHLY_BUDGET_USD / 30):  # Daily budget
            logger.warning(
                f"[{self.dag_id}] Daily budget threshold exceeded: "
                f"${self.total_cost:.2f} > ${MONTHLY_BUDGET_USD/30:.2f}"
            )
            return False
        return True

    def get_summary(self) -> Dict[str, Any]:
        """Get DAG run summary"""
        duration = (datetime.now() - self.start_time).total_seconds()

        return {
            'dag_id': self.dag_id,
            'run_id': self.run_id,
            'total_duration': duration,
            'total_cost': self.total_cost,
            'records_processed': self.records_processed,
            'task_count': len(self.task_metrics),
            'failed_tasks': sum(
                1 for t in self.task_metrics.values()
                if t.get('status') == 'failed'
            )
        }


# Global metrics instance (will be created per DAG run)
metrics: OperationalMetrics = None


def initialize_metrics(**context):
    """Initialize operational metrics for DAG run"""
    global metrics
    dag_id = context['dag'].dag_id
    run_id = context['run_id']
    metrics = OperationalMetrics(dag_id, run_id)
    logger.info(f"Initialized metrics for DAG run {run_id}")


def ingest_ergast_seasons(**context):
    """Ingest season data from Ergast API"""
    global metrics
    task_id = context['task'].task_id
    metrics.record_task_start(task_id)

    try:
        client = ErgastClient()
        seasons = client.get_seasons(start_year=1950, end_year=2024)

        DATA_RECORDS_INGESTED.labels(
            data_source='ergast',
            data_type='seasons'
        ).inc(len(seasons))

        metrics.record_task_end(task_id, 'success', len(seasons))

        # Push to XCom for downstream tasks
        context['task_instance'].xcom_push(key='seasons', value=seasons)

        logger.info(f"Ingested {len(seasons)} seasons from Ergast")
        return {'seasons_count': len(seasons)}

    except Exception as e:
        metrics.record_task_end(task_id, 'failed')
        logger.error(f"Failed to ingest seasons: {e}")
        raise AirflowException(f"Ergast seasons ingestion failed: {e}")


def ingest_ergast_drivers(**context):
    """Ingest driver data from Ergast API"""
    global metrics
    task_id = context['task'].task_id
    metrics.record_task_start(task_id)

    try:
        client = ErgastClient()
        drivers = client.get_drivers()

        DATA_RECORDS_INGESTED.labels(
            data_source='ergast',
            data_type='drivers'
        ).inc(len(drivers))

        metrics.record_task_end(task_id, 'success', len(drivers))

        context['task_instance'].xcom_push(
            key='drivers',
            value=[d.dict() for d in drivers]
        )

        logger.info(f"Ingested {len(drivers)} drivers from Ergast")
        return {'drivers_count': len(drivers)}

    except Exception as e:
        metrics.record_task_end(task_id, 'failed')
        logger.error(f"Failed to ingest drivers: {e}")
        raise AirflowException(f"Ergast drivers ingestion failed: {e}")


def ingest_ergast_races(**context):
    """Ingest race data for recent seasons"""
    global metrics
    task_id = context['task'].task_id
    metrics.record_task_start(task_id)

    try:
        # Get seasons from upstream task
        seasons = context['task_instance'].xcom_pull(
            task_ids='ingest_ergast_seasons',
            key='seasons'
        ) or [2023, 2024]  # Default to recent years

        client = ErgastClient()
        total_races = 0

        for year in seasons[-2:]:  # Last 2 seasons for demo
            races = client.get_races(year)
            total_races += len(races)

            DATA_RECORDS_INGESTED.labels(
                data_source='ergast',
                data_type='races'
            ).inc(len(races))

        metrics.record_task_end(task_id, 'success', total_races)

        logger.info(f"Ingested {total_races} races from Ergast")
        return {'races_count': total_races}

    except Exception as e:
        metrics.record_task_end(task_id, 'failed')
        logger.error(f"Failed to ingest races: {e}")
        raise AirflowException(f"Ergast races ingestion failed: {e}")


def ingest_fastf1_events(**context):
    """Ingest event schedule from FastF1"""
    global metrics
    task_id = context['task'].task_id
    metrics.record_task_start(task_id)

    try:
        client = FastF1Client()
        events = client.get_available_events(2024)

        DATA_RECORDS_INGESTED.labels(
            data_source='fastf1',
            data_type='events'
        ).inc(len(events))

        metrics.record_task_end(task_id, 'success', len(events))

        context['task_instance'].xcom_push(key='events', value=events)

        logger.info(f"Ingested {len(events)} events from FastF1")
        return {'events_count': len(events)}

    except Exception as e:
        metrics.record_task_end(task_id, 'failed')
        logger.error(f"Failed to ingest FastF1 events: {e}")
        raise AirflowException(f"FastF1 events ingestion failed: {e}")


def check_budget_threshold(**context):
    """Check if budget threshold exceeded"""
    global metrics

    if not metrics.check_budget():
        logger.warning("Budget threshold exceeded - consider throttling")
        # In production, could trigger alerts or pause non-critical tasks
        # For now, just log the warning
        pass

    summary = metrics.get_summary()
    logger.info(f"DAG run summary: {summary}")

    return summary


def publish_metrics(**context):
    """Publish final DAG run metrics"""
    global metrics
    summary = metrics.get_summary()

    # Update Prometheus metrics
    DAG_RUN_DURATION.labels(
        dag_id=summary['dag_id'],
        status='success' if summary['failed_tasks'] == 0 else 'partial_failure'
    ).observe(summary['total_duration'])

    logger.info(f"Published metrics for DAG run {summary['run_id']}")
    return summary


# Default DAG arguments
default_args = {
    'owner': 'f1-strategy-optimizer',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=2),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=10),
    'execution_timeout': timedelta(minutes=30),
}

# Create DAG
dag = DAG(
    dag_id='f1_data_ingestion',
    default_args=default_args,
    description='Ingest F1 data from Ergast and FastF1 with operational guarantees',
    schedule_interval='@daily',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=['f1', 'data-ingestion', 'production'],
    doc_md=__doc__,
    sla_miss_callback=lambda context: logger.warning(
        f"SLA missed for task {context['task'].task_id}"
    )
)

with dag:
    # Start task
    start = EmptyOperator(
        task_id='start',
        dag=dag
    )

    # Initialize metrics
    init_metrics = PythonOperator(
        task_id='initialize_metrics',
        python_callable=initialize_metrics,
        provide_context=True,
        dag=dag
    )

    # Ergast ingestion tasks
    with TaskGroup('ergast_ingestion', tooltip='Ingest data from Ergast API') as ergast_group:
        ingest_seasons = PythonOperator(
            task_id='ingest_ergast_seasons',
            python_callable=ingest_ergast_seasons,
            provide_context=True,
            dag=dag
        )

        ingest_drivers = PythonOperator(
            task_id='ingest_ergast_drivers',
            python_callable=ingest_ergast_drivers,
            provide_context=True,
            dag=dag
        )

        ingest_races = PythonOperator(
            task_id='ingest_ergast_races',
            python_callable=ingest_ergast_races,
            provide_context=True,
            dag=dag
        )

        # Dependencies within group
        ingest_seasons >> ingest_races
        [ingest_seasons, ingest_drivers]

    # FastF1 ingestion tasks
    with TaskGroup('fastf1_ingestion', tooltip='Ingest data from FastF1') as fastf1_group:
        ingest_events = PythonOperator(
            task_id='ingest_fastf1_events',
            python_callable=ingest_fastf1_events,
            provide_context=True,
            dag=dag
        )

    # Budget check
    check_budget = PythonOperator(
        task_id='check_budget_threshold',
        python_callable=check_budget_threshold,
        provide_context=True,
        dag=dag
    )

    # Publish metrics
    publish = PythonOperator(
        task_id='publish_metrics',
        python_callable=publish_metrics,
        provide_context=True,
        trigger_rule='all_done',  # Run even if upstream tasks failed
        dag=dag
    )

    # End task
    end = EmptyOperator(
        task_id='end',
        trigger_rule='all_done',
        dag=dag
    )

    # Define DAG structure
    start >> init_metrics >> [ergast_group, fastf1_group] >> check_budget >> publish >> end
