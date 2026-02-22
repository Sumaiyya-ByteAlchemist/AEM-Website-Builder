"""AEM Deployer - Deploys packages and bundles to AEM instances."""

import logging
import subprocess
import time
from pathlib import Path

import requests

from ..utils.aem_utils import AEMUtils

logger = logging.getLogger(__name__)


class AEMDeployer:
    """Deploys AEM content packages and OSGi bundles to running AEM instances.

    Supports:
    - Maven build and deploy (mvn clean install -PautoInstallSinglePackage)
    - Package Manager upload and install
    - OSGi bundle deployment
    """

    def __init__(self, config: dict):
        self.config = config.get("deployment", {})
        self.aem_utils = AEMUtils(config)

        # Instance connection details
        self.author_url = config.get("deployment", {}).get("sdk", {}).get(
            "author_url", "http://localhost:4502"
        )
        self.admin_user = "admin"
        self.admin_password = "admin"

    def maven_build_and_deploy(
        self,
        project_dir: str,
        profiles: list = None,
        skip_tests: bool = False,
    ) -> bool:
        """Build and deploy the AEM project using Maven.

        Args:
            project_dir: Path to the AEM project root (with pom.xml).
            profiles: Maven profiles to activate.
            skip_tests: Whether to skip tests.

        Returns:
            True if build and deployment succeeded.
        """
        if profiles is None:
            profiles = ["autoInstallSinglePackage"]

        cmd = ["mvn", "clean", "install"]

        for profile in profiles:
            cmd.append(f"-P{profile}")

        if skip_tests:
            cmd.append("-DskipTests")

        # Set AEM connection properties
        cmd.extend([
            f"-Daem.host=localhost",
            f"-Daem.port={self._extract_port(self.author_url)}",
        ])

        logger.info(f"Building and deploying: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            if result.returncode == 0:
                logger.info("Maven build and deploy succeeded")
                return True
            else:
                logger.error(f"Maven build failed:\n{result.stdout}\n{result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Maven build timed out")
            return False
        except FileNotFoundError:
            logger.error("Maven (mvn) not found. Ensure Maven is installed and in PATH.")
            return False

    def deploy_package(self, package_path: str) -> bool:
        """Deploy a content package via AEM Package Manager.

        Args:
            package_path: Path to the .zip package file.

        Returns:
            True if deployment succeeded.
        """
        package_file = Path(package_path)
        if not package_file.exists():
            logger.error(f"Package not found: {package_path}")
            return False

        # Step 1: Upload package
        logger.info(f"Uploading package: {package_file.name}")
        upload_url = f"{self.author_url}/crx/packmgr/service.jsp"

        try:
            with open(package_path, "rb") as f:
                response = requests.post(
                    upload_url,
                    files={"package": (package_file.name, f, "application/zip")},
                    data={"cmd": "upload", "force": "true"},
                    auth=(self.admin_user, self.admin_password),
                    timeout=120,
                )

            if response.status_code != 200 or "200" not in response.text:
                logger.error(f"Package upload failed: {response.text}")
                return False

            logger.info("Package uploaded successfully")

            # Step 2: Install package
            # Extract package path from upload response
            install_url = f"{self.author_url}/crx/packmgr/service.jsp"
            response = requests.post(
                install_url,
                data={
                    "cmd": "inst",
                    "name": package_file.stem,
                },
                auth=(self.admin_user, self.admin_password),
                timeout=120,
            )

            if response.status_code == 200:
                logger.info("Package installed successfully")
                return True
            else:
                logger.error(f"Package installation failed: {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"Package deployment failed: {e}")
            return False

    def deploy_bundle(self, bundle_path: str) -> bool:
        """Deploy an OSGi bundle to AEM.

        Args:
            bundle_path: Path to the .jar bundle file.

        Returns:
            True if deployment succeeded.
        """
        bundle_file = Path(bundle_path)
        if not bundle_file.exists():
            logger.error(f"Bundle not found: {bundle_path}")
            return False

        logger.info(f"Deploying bundle: {bundle_file.name}")
        install_url = f"{self.author_url}/system/console/bundles"

        try:
            with open(bundle_path, "rb") as f:
                response = requests.post(
                    install_url,
                    files={"bundlefile": (bundle_file.name, f, "application/java-archive")},
                    data={
                        "action": "install",
                        "bundlestartlevel": "20",
                        "bundlestart": "start",
                        "refreshPackages": "true",
                    },
                    auth=(self.admin_user, self.admin_password),
                    timeout=60,
                )

            if response.status_code in (200, 302):
                logger.info("Bundle deployed successfully")
                return True
            else:
                logger.error(f"Bundle deployment failed: {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.error(f"Bundle deployment failed: {e}")
            return False

    def deploy_clientlib(self, clientlib_dir: str) -> bool:
        """Deploy client libraries by building and deploying the ui.apps module.

        Args:
            clientlib_dir: Path to the clientlib directory within ui.apps.

        Returns:
            True if succeeded.
        """
        # Find the ui.apps module root
        path = Path(clientlib_dir)
        while path.name != "ui.apps" and path.parent != path:
            path = path.parent

        if path.name != "ui.apps":
            logger.error("Could not find ui.apps module root")
            return False

        return self.maven_build_and_deploy(
            str(path),
            profiles=["autoInstallPackage"],
            skip_tests=True,
        )

    def wait_for_deployment(self, timeout: int = 60) -> bool:
        """Wait for AEM to finish processing a deployment.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if AEM is stable.
        """
        logger.info("Waiting for AEM to stabilize after deployment...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.author_url}/system/console/bundles.json",
                    auth=(self.admin_user, self.admin_password),
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("s", [])
                    # s[3] = installed (not resolved), s[4] = resolved (not active)
                    if len(status) >= 5 and status[3] == 0 and status[4] == 0:
                        logger.info("AEM is stable")
                        return True
            except requests.RequestException:
                pass

            time.sleep(5)

        logger.warning("AEM did not stabilize within timeout")
        return False

    def _extract_port(self, url: str) -> int:
        """Extract port number from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.port or 4502
