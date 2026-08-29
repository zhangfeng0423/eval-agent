"""
sandbox.py — Unified Sandbox Abstraction for UTM (Ubuntu VM), OrbStack, and Docker isolation.
"""

import os
import time
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SandboxExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    timed_out: bool = False

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def full_output(self) -> str:
        return (
            f"[Exit Code]: {self.exit_code}\n"
            f"[STDOUT]:\n{self.stdout}\n"
            f"[STDERR]:\n{self.stderr}"
        )


class SandboxProvider(ABC):
    """Abstract interface for all sandbox execution environments."""

    @abstractmethod
    def exec_command(
        self,
        cmd: str,
        work_dir: Optional[str] = None,
        timeout_seconds: int = 60,
        env_vars: Optional[Dict[str, str]] = None
    ) -> SandboxExecutionResult:
        pass

    @abstractmethod
    def reset_environment(self) -> bool:
        pass


class UTMSandbox(SandboxProvider):
    """Executes commands inside a UTM Ubuntu VM via SSH."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2222,
        user: str = "ubuntu",
        ssh_key_path: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.user = user
        self.ssh_key_path = ssh_key_path

    def exec_command(
        self,
        cmd: str,
        work_dir: Optional[str] = None,
        timeout_seconds: int = 60,
        env_vars: Optional[Dict[str, str]] = None
    ) -> SandboxExecutionResult:
        full_cmd = f"cd {work_dir} && {cmd}" if work_dir else cmd

        ssh_args = [
            "ssh",
            "-p", str(self.port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=5",
            "-o", "LogLevel=ERROR",
        ]
        if self.ssh_key_path and os.path.exists(self.ssh_key_path):
            ssh_args.extend(["-i", self.ssh_key_path])

        ssh_args.extend([f"{self.user}@{self.host}", full_cmd])

        start_t = time.time()
        try:
            proc = subprocess.run(
                ssh_args,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=elapsed,
                timed_out=False
            )
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=124,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\n[UTM Sandbox]: Command timed out after {timeout_seconds}s.",
                elapsed_seconds=elapsed,
                timed_out=True
            )
        except Exception as e:
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"[UTM Sandbox Error]: {str(e)}",
                elapsed_seconds=elapsed,
                timed_out=False
            )

    def reset_environment(self) -> bool:
        # Optional: invoke UTM snapshot restoration if configured
        logger.info("UTM Sandbox environment reset request")
        return True


class OrbStackSandbox(SandboxProvider):
    """Executes commands inside an OrbStack Linux machine / container."""

    def __init__(self, machine_name: str = "eval-runner"):
        self.machine_name = machine_name

    def exec_command(
        self,
        cmd: str,
        work_dir: Optional[str] = None,
        timeout_seconds: int = 60,
        env_vars: Optional[Dict[str, str]] = None
    ) -> SandboxExecutionResult:
        full_cmd = f"cd {work_dir} && {cmd}" if work_dir else cmd
        exec_args = ["orb", "run", "-m", self.machine_name, "bash", "-c", full_cmd]

        start_t = time.time()
        try:
            proc = subprocess.run(
                exec_args,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=elapsed,
                timed_out=False
            )
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=124,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\n[OrbStack Sandbox]: Command timed out after {timeout_seconds}s.",
                elapsed_seconds=elapsed,
                timed_out=True
            )
        except Exception as e:
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"[OrbStack Sandbox Error]: {str(e)}",
                elapsed_seconds=elapsed,
                timed_out=False
            )

    def reset_environment(self) -> bool:
        logger.info("OrbStack Sandbox environment reset request")
        return True


class LocalSandbox(SandboxProvider):
    """Local subprocess execution fallback for testing."""

    def exec_command(
        self,
        cmd: str,
        work_dir: Optional[str] = None,
        timeout_seconds: int = 60,
        env_vars: Optional[Dict[str, str]] = None
    ) -> SandboxExecutionResult:
        start_t = time.time()
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={**os.environ, **(env_vars or {})}
            )
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=elapsed,
                timed_out=False
            )
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=124,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\n[Local Sandbox]: Command timed out after {timeout_seconds}s.",
                elapsed_seconds=elapsed,
                timed_out=True
            )
        except Exception as e:
            elapsed = time.time() - start_t
            return SandboxExecutionResult(
                exit_code=1,
                stdout="",
                stderr=f"[Local Sandbox Error]: {str(e)}",
                elapsed_seconds=elapsed,
                timed_out=False
            )

    def reset_environment(self) -> bool:
        return True


def create_sandbox(sandbox_type: str = "utm", **kwargs) -> SandboxProvider:
    """Factory to instantiate the desired sandbox provider."""
    st = sandbox_type.lower()
    if st == "utm":
        return UTMSandbox(**kwargs)
    elif st == "orbstack":
        return OrbStackSandbox(**kwargs)
    elif st == "local":
        return LocalSandbox()
    else:
        raise ValueError(f"Unsupported sandbox type: {sandbox_type}")
