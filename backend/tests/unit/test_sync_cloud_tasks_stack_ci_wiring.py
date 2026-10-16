"""Static wiring contract for the blocking Sync Cloud Tasks stack gauntlet.

Behavior is proved by the emulator stack itself.  This test prevents its
package script, high-risk workflow contract, or blocking CI job from silently
disconnecting.
"""

from __future__ import annotations

import json

from google.cloud import tasks_v2
from google.protobuf import duration_pb2
from testing.sync_cloud_tasks_stack.cloud_tasks import CloudTasksRecorder
from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS, SYNC_JOB_TASK_PAYLOAD_KEYS

# Keep in lockstep with test_listen_pusher_stack_ci_wiring._BOUNDED_APT_GET:
# unbounded apt-get is the hang that previously burned this job's timeout.
_BOUNDED_APT_GET = 'sudo apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=10 -o Acquire::https::Timeout=10'


def test_gauntlet_recorder_shares_the_production_task_payload_schema(monkeypatch, tmp_path) -> None:
    """The recorder must accept every durable field admission can enqueue."""
    handler_url = 'http://127.0.0.1:39123/v2/sync-jobs/run'
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'test-project')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'us-central1')
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', handler_url)
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', handler_url)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@test-project.iam.gserviceaccount.com')
    monkeypatch.setenv('OMI_SYNC_STACK_STATE_DIR', str(tmp_path))

    payload = {key: None for key in SYNC_JOB_TASK_PAYLOAD_KEYS}
    payload.update(
        {
            'schema_version': 1,
            'job_id': 'job-1',
            'raw_blob_paths': ['gs://sync/job-1.opus'],
        }
    )
    recorder = CloudTasksRecorder()
    task = tasks_v2.Task(
        name=recorder.task_path('test-project', 'us-central1', 'sync-jobs', 'job-1'),
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=handler_url,
            headers={'Content-Type': 'application/json'},
            body=json.dumps(payload).encode('utf-8'),
            oidc_token=tasks_v2.OidcToken(
                service_account_email='invoker@test-project.iam.gserviceaccount.com',
                audience=handler_url,
            ),
        ),
        dispatch_deadline=duration_pb2.Duration(seconds=DISPATCH_DEADLINE_SECONDS),
    )

    assert (
        recorder.create_task(parent=recorder.queue_path('test-project', 'us-central1', 'sync-jobs'), task=task) is task
    )
    assert recorder._tasks['job-1'].body == payload
