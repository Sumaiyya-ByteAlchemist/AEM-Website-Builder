"""AEM SDK Manager - Manages AEM local SDK instance lifecycle."""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class AEMSDKManager:
    """Manages the AEM local SDK for development and testing.

    Handles:
    - SDK JAR discovery and setup
    - Starting/stopping AEM author and publish instances
    - Health checks and readiness verification
    - Run mode configuration
    """

    def __init__(self, config: dict):
        deploy_config = config.get("deployment", {}).get("sdk", {})
        self.sdk_path = os.environ.get("AEM_SDK_PATH", deploy_config.get("sdk_path", ""))
        self.author_port = deploy_config.get("port_author", 4502)
        self.publish_port = deploy_config.get("port_publish", 4503)
        self.run_modes = deploy_config.get("run_modes", ["author", "nosamplecontent"])
        self.jvm_args = deploy_config.get("jvm_args", "-Xmx2048m")

        self.author_url = os.environ.get("AEM_AUTHOR_URL", f"http://localhost:{self.author_port}")
        self.publish_url = os.environ.get("AEM_PUBLISH_URL", f"http://localhost:{self.publish_port}")
        self.admin_user = os.environ.get("AEM_ADMIN_USER", "admin")
        self.admin_password = os.environ.get("AEM_ADMIN_PASSWORD", "admin")

        self._author_process = None
        self._publish_process = None

    def find_sdk_jar(self) -> Optional[str]:
        """Find the AEM SDK quickstart JAR file.

        Returns:
            Path to the JAR file, or None if not found.
        """
        if not self.sdk_path:
            logger.error("AEM_SDK_PATH not set")
            return None

        sdk_dir = Path(self.sdk_path)
        if not sdk_dir.exists():
            logger.error(f"SDK directory not found: {self.sdk_path}")
            return None

        # Look for quickstart JAR
        patterns = ["aem-sdk-quickstart-*.jar", "cq-quickstart-*.jar", "aem-author-*.jar"]
        for pattern in patterns:
            jars = list(sdk_dir.glob(pattern))
            if jars:
                jar = sorted(jars, reverse=True)[0]  # Latest version
                logger.info(f"Found SDK JAR: {jar}")
                return str(jar)

        # Check for already-unpacked crx-quickstart
        crx_dir = sdk_dir / "crx-quickstart"
        if crx_dir.exists():
            logger.info(f"Found unpacked SDK at: {sdk_dir}")
            return str(sdk_dir)

        logger.error(f"No AEM SDK JAR found in {self.sdk_path}")
        return None

    def start_author(self, wait_for_ready: bool = True) -> bool:
        """Start the AEM author instance.

        Args:
            wait_for_ready: Whether to wait for the instance to be fully ready.

        Returns:
            True if started successfully.
        """
        jar_path = self.find_sdk_jar()
        if not jar_path:
            return False

        logger.info(f"Starting AEM author on port {self.author_port}...")

        run_modes_str = ",".join(self.run_modes)
        cmd = [
            "java",
            *self.jvm_args.split(),
            "-jar", jar_path,
            f"-p", str(self.author_port),
            f"-r", run_modes_str,
            "-nointeractive",
        ]

        try:
            self._author_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(jar_path),
            )
            logger.info(f"AEM author process started (PID: {self._author_process.pid})")

            if wait_for_ready:
                return self._wait_for_ready(self.author_url)

            return True
        except Exception as e:
            logger.error(f"Failed to start AEM author: {e}")
            return False

    def stop_author(self) -> bool:
        """Stop the AEM author instance."""
        return self._stop_instance(self._author_process, self.author_url, "author")

    def start_publish(self, wait_for_ready: bool = True) -> bool:
        """Start the AEM publish instance."""
        jar_path = self.find_sdk_jar()
        if not jar_path:
            return False

        logger.info(f"Starting AEM publish on port {self.publish_port}...")
        cmd = [
            "java",
            *self.jvm_args.split(),
            "-jar", jar_path,
            f"-p", str(self.publish_port),
            "-r", "publish,nosamplecontent",
            "-nointeractive",
        ]

        try:
            self._publish_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(jar_path),
            )
            logger.info(f"AEM publish process started (PID: {self._publish_process.pid})")

            if wait_for_ready:
                return self._wait_for_ready(self.publish_url)

            return True
        except Exception as e:
            logger.error(f"Failed to start AEM publish: {e}")
            return False

    def stop_publish(self) -> bool:
        """Stop the AEM publish instance."""
        return self._stop_instance(self._publish_process, self.publish_url, "publish")

    def is_running(self, instance_type: str = "author") -> bool:
        """Check if an AEM instance is running and responsive.

        Args:
            instance_type: 'author' or 'publish'.

        Returns:
            True if the instance is running.
        """
        url = self.author_url if instance_type == "author" else self.publish_url
        try:
            response = requests.get(
                f"{url}/system/health",
                auth=(self.admin_user, self.admin_password),
                timeout=5,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_instance_info(self, instance_type: str = "author") -> dict:
        """Get information about a running AEM instance.

        Returns:
            Dict with instance details.
        """
        url = self.author_url if instance_type == "author" else self.publish_url
        info = {
            "type": instance_type,
            "url": url,
            "running": False,
            "version": "unknown",
        }

        try:
            # Check system console
            response = requests.get(
                f"{url}/system/console/status-productinfo.txt",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )
            if response.status_code == 200:
                info["running"] = True
                # Parse version from response
                for line in response.text.split("\n"):
                    if "Adobe Experience Manager" in line:
                        info["version"] = line.strip()
                        break
        except requests.RequestException:
            pass

        return info

    def _wait_for_ready(self, url: str, max_wait: int = 300, interval: int = 10) -> bool:
        """Wait for an AEM instance to be fully ready.

        Args:
            url: Instance URL.
            max_wait: Maximum seconds to wait.
            interval: Seconds between checks.

        Returns:
            True if ready within timeout.
        """
        logger.info(f"Waiting for AEM at {url} to be ready (max {max_wait}s)...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                # Check login page availability
                response = requests.get(
                    f"{url}/libs/granite/core/content/login.html",
                    timeout=10,
                    allow_redirects=False,
                )
                if response.status_code in (200, 302):
                    # Also check OSGi bundles are active
                    bundles_response = requests.get(
                        f"{url}/system/console/bundles.json",
                        auth=(self.admin_user, self.admin_password),
                        timeout=10,
                    )
                    if bundles_response.status_code == 200:
                        data = bundles_response.json()
                        # Check no bundles are in "Installed" state (should be "Active")
                        status = data.get("s", [])
                        if len(status) >= 5 and status[3] == 0 and status[4] == 0:
                            logger.info(f"AEM is ready at {url}")
                            return True
            except requests.RequestException:
                pass

            logger.info(f"AEM not ready yet, waiting {interval}s...")
            time.sleep(interval)

        logger.error(f"AEM did not become ready within {max_wait}s")
        return False

    def _stop_instance(self, process, url: str, name: str) -> bool:
        """Stop an AEM instance."""
        logger.info(f"Stopping AEM {name}...")

        # Try graceful shutdown via API
        try:
            requests.post(
                f"{url}/system/console/vmstat",
                data={"shutdown_type": "Stop"},
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )
            time.sleep(5)
        except requests.RequestException:
            pass

        # Force kill if process handle available
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()

        logger.info(f"AEM {name} stopped")
        return True
