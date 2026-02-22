"""AEM Validator - Validates deployed components, templates, and content."""

import json
import logging
from dataclasses import dataclass, field

import requests

from ..utils.aem_utils import AEMUtils

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""

    check: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report."""

    results: list[ValidationResult] = field(default_factory=list)
    total_checks: int = 0
    passed: int = 0
    failed: int = 0

    def add_result(self, result: ValidationResult):
        self.results.append(result)
        self.total_checks += 1
        if result.passed:
            self.passed += 1
        else:
            self.failed += 1

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": self.total_checks,
                "passed": self.passed,
                "failed": self.failed,
                "status": "PASS" if self.all_passed else "FAIL",
            },
            "results": [
                {
                    "check": r.check,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.results
            ],
        }

    def print_report(self) -> str:
        lines = [
            "=" * 60,
            "AEM DEPLOYMENT VALIDATION REPORT",
            "=" * 60,
            "",
            f"Total Checks: {self.total_checks}",
            f"Passed: {self.passed}",
            f"Failed: {self.failed}",
            f"Status: {'PASS' if self.all_passed else 'FAIL'}",
            "",
            "-" * 60,
        ]

        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.check}: {r.message}")

        lines.append("=" * 60)
        return "\n".join(lines)


class AEMValidator:
    """Validates AEM deployments by checking components, templates, and content.

    Performs post-deployment validation to ensure all generated artifacts
    are correctly installed and functional.
    """

    def __init__(self, config: dict):
        self.config = config.get("deployment", {}).get("validation", {})
        self.aem_utils = AEMUtils(config)

        deploy_config = config.get("deployment", {}).get("sdk", {})
        self.author_url = f"http://localhost:{deploy_config.get('port_author', 4502)}"
        self.admin_user = "admin"
        self.admin_password = "admin"

    def validate_all(self, component_names: list, template_names: list = None) -> ValidationReport:
        """Run all validation checks.

        Args:
            component_names: List of component names to validate.
            template_names: List of template names to validate.

        Returns:
            ValidationReport with all results.
        """
        report = ValidationReport()

        # Check AEM instance is running
        report.add_result(self._check_instance_health())

        if not report.results[-1].passed:
            logger.error("AEM instance is not healthy, skipping further checks")
            return report

        # Check OSGi bundles
        report.add_result(self._check_bundles())

        # Check components
        if self.config.get("check_components", True):
            for name in component_names:
                report.add_result(self._check_component(name))

        # Check templates
        if self.config.get("check_templates", True) and template_names:
            for name in template_names:
                report.add_result(self._check_template(name))

        # Check content structure
        if self.config.get("check_content", True):
            report.add_result(self._check_content_structure())

        # Check clientlibs
        if self.config.get("check_clientlibs", True):
            report.add_result(self._check_clientlibs())

        return report

    def _check_instance_health(self) -> ValidationResult:
        """Check if the AEM instance is healthy."""
        try:
            response = requests.get(
                f"{self.author_url}/system/health",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )
            if response.status_code == 200:
                return ValidationResult(
                    check="Instance Health",
                    passed=True,
                    message="AEM instance is healthy",
                )
        except requests.RequestException as e:
            return ValidationResult(
                check="Instance Health",
                passed=False,
                message=f"AEM instance is not reachable: {e}",
            )

        return ValidationResult(
            check="Instance Health",
            passed=False,
            message=f"AEM instance returned status {response.status_code}",
        )

    def _check_bundles(self) -> ValidationResult:
        """Check that all OSGi bundles are active."""
        try:
            response = requests.get(
                f"{self.author_url}/system/console/bundles.json",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("s", [])
                total = status[0] if len(status) > 0 else 0
                active = status[1] if len(status) > 1 else 0
                installed = status[3] if len(status) > 3 else 0
                resolved = status[4] if len(status) > 4 else 0

                if installed == 0 and resolved == 0:
                    return ValidationResult(
                        check="OSGi Bundles",
                        passed=True,
                        message=f"All {total} bundles are active",
                        details={"total": total, "active": active},
                    )
                else:
                    return ValidationResult(
                        check="OSGi Bundles",
                        passed=False,
                        message=f"{installed} installed, {resolved} resolved bundles found",
                        details={"total": total, "active": active, "installed": installed, "resolved": resolved},
                    )
        except requests.RequestException as e:
            return ValidationResult(
                check="OSGi Bundles",
                passed=False,
                message=f"Failed to check bundles: {e}",
            )

        return ValidationResult(check="OSGi Bundles", passed=False, message="Unknown error")

    def _check_component(self, component_name: str) -> ValidationResult:
        """Check if a component is properly deployed."""
        component_path = self.aem_utils.get_component_path(component_name)

        try:
            # Check if the component node exists
            response = requests.get(
                f"{self.author_url}{component_path}.json",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                has_dialog = "_cq_dialog" in data
                return ValidationResult(
                    check=f"Component: {component_name}",
                    passed=True,
                    message=f"Component exists at {component_path}" + (" (with dialog)" if has_dialog else ""),
                    details={"path": component_path, "has_dialog": has_dialog},
                )
            else:
                return ValidationResult(
                    check=f"Component: {component_name}",
                    passed=False,
                    message=f"Component not found at {component_path}",
                )
        except requests.RequestException as e:
            return ValidationResult(
                check=f"Component: {component_name}",
                passed=False,
                message=f"Failed to check component: {e}",
            )

    def _check_template(self, template_name: str) -> ValidationResult:
        """Check if a template is properly deployed and enabled."""
        template_path = self.aem_utils.get_template_path(template_name)

        try:
            response = requests.get(
                f"{self.author_url}{template_path}.json",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                return ValidationResult(
                    check=f"Template: {template_name}",
                    passed=True,
                    message=f"Template exists (status: {status})",
                    details={"path": template_path, "status": status},
                )
            else:
                return ValidationResult(
                    check=f"Template: {template_name}",
                    passed=False,
                    message=f"Template not found at {template_path}",
                )
        except requests.RequestException as e:
            return ValidationResult(
                check=f"Template: {template_name}",
                passed=False,
                message=f"Failed to check template: {e}",
            )

    def _check_content_structure(self) -> ValidationResult:
        """Check if the content structure was created."""
        content_path = self.aem_utils.get_content_path()

        try:
            response = requests.get(
                f"{self.author_url}{content_path}.json",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )

            if response.status_code == 200:
                return ValidationResult(
                    check="Content Structure",
                    passed=True,
                    message=f"Content root exists at {content_path}",
                )
            else:
                return ValidationResult(
                    check="Content Structure",
                    passed=False,
                    message=f"Content root not found at {content_path}",
                )
        except requests.RequestException as e:
            return ValidationResult(
                check="Content Structure",
                passed=False,
                message=f"Failed to check content: {e}",
            )

    def _check_clientlibs(self) -> ValidationResult:
        """Check if client libraries are loading."""
        app_id = self.aem_utils.app_id

        try:
            # Check if base clientlib is accessible
            response = requests.get(
                f"{self.author_url}/etc.clientlibs/{app_id}/clientlibs/clientlib-base.css",
                auth=(self.admin_user, self.admin_password),
                timeout=10,
            )

            if response.status_code == 200:
                return ValidationResult(
                    check="Client Libraries",
                    passed=True,
                    message="Base clientlib is accessible",
                )
            else:
                return ValidationResult(
                    check="Client Libraries",
                    passed=False,
                    message=f"Base clientlib returned status {response.status_code}",
                )
        except requests.RequestException as e:
            return ValidationResult(
                check="Client Libraries",
                passed=False,
                message=f"Failed to check clientlibs: {e}",
            )
