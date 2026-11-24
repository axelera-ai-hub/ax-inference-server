"""Background poller that samples the host server AxMonitor stats endpoint during a test.

Exposes AxMonitorTracer, enabled only when AXMONITOR_TRACE=1.

Note:
    Environment: AXMONITOR_API_KEY (required when enabled), AXMONITOR_HOST_SERVER_URL (optional;
    defaults to the scheme and hostname of the base URL on port 8088).
"""

import json
import os
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse


class AxMonitorTracer:
    """Polls /api/v1/monitor/stats on a daemon thread and keeps every sample.

    Becomes a no-op (enabled is False) when tracing is off or the API key is missing.

    Attributes:
        enabled (bool): True only when AXMONITOR_TRACE=1 and an API key is available.
        interval_s (float): Seconds between polls.
        samples (list): Parsed JSON stats, or {'_error': message} for a failed poll.
        error (str | None): Reason tracing was disabled, if any.
        stats_url (str): Full stats URL. Set only when enabled.
        api_key (str): Value sent in the X-API-Key header. Set only when enabled.

    Note:
        The samples list is appended from the polling thread and read after stop().
    """
    def __init__(self, base_url, interval_s=1.0):
        """Configure the tracer from the environment.

        Args:
            base_url (str): Server URL used to derive the host server URL when AXMONITOR_HOST_SERVER_URL is unset.
            interval_s (float, optional): Seconds between polls. Defaults to 1.0.
        """
        self.enabled = os.environ.get('AXMONITOR_TRACE') == '1'
        self.interval_s = interval_s
        self.samples = []
        self.error = None
        self._stop = threading.Event()
        self._thread = None
        if not self.enabled:
            return

        api_key = os.environ.get('AXMONITOR_API_KEY')
        if not api_key:
            self.error = 'AXMONITOR_TRACE=1 but AXMONITOR_API_KEY is not set -- skipping trace'
            self.enabled = False
            return

        host_server_url = os.environ.get('AXMONITOR_HOST_SERVER_URL')
        if not host_server_url:
            parsed = urlparse(base_url)
            host_server_url = f'{parsed.scheme}://{parsed.hostname}:8088'
        self.stats_url = host_server_url.rstrip('/') + '/api/v1/monitor/stats'
        self.api_key = api_key

    def start(self):
        """Start the polling thread. Does nothing when disabled."""
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the polling thread to stop and wait up to 5 s for it to exit."""
        if not self.enabled or not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=5)

    def _poll_loop(self):
        """Fetch the stats endpoint every interval_s seconds until stopped, recording each result or error."""
        while not self._stop.is_set():
            try:
                req = urllib.request.Request(self.stats_url, headers={'X-API-Key': self.api_key})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    self.samples.append(json.loads(resp.read()))
            except Exception as exc:
                self.samples.append({'_error': str(exc)})
            self._stop.wait(self.interval_s)

    def summarize(self):
        """Reduce the collected samples to peak utilisation figures.

        Returns:
            dict | None: None when disabled. Otherwise sample_count, error_count, max_core_utilization_pct
            and max_ddr_utilization_pct (maximum over all devices and samples; 0.0 if none reported).
        """

        if not self.enabled:
            return None
        max_core = 0.0
        max_ddr = 0.0
        errors = 0
        for sample in self.samples:
            if '_error' in sample:
                errors += 1
                continue
            for dev in (sample.get('devices') or {}).values():
                core = dev.get('sys_core_utilization_pct')
                ddr = dev.get('ddr_utilization_pct')
                if isinstance(core, (int, float)):
                    max_core = max(max_core, core)
                if isinstance(ddr, (int, float)):
                    max_ddr = max(max_ddr, ddr)
        return {
            'sample_count': len(self.samples),
            'error_count': errors,
            'max_core_utilization_pct': max_core,
            'max_ddr_utilization_pct': max_ddr,
        }
