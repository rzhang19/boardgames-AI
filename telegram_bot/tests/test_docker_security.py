import os
import pytest

COMPOSE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "docker-compose.yml"
)


def read_compose():
    with open(COMPOSE_PATH) as f:
        return f.read()


@pytest.mark.unit
class TestDockerSocketProxyService:
    def test_socket_proxy_service_exists(self):
        content = read_compose()
        assert "socket-proxy:" in content

    def test_socket_proxy_uses_tecnativa_image(self):
        content = read_compose()
        assert "tecnativa/docker-socket-proxy" in content

    def test_socket_proxy_mounts_docker_socket(self):
        content = read_compose()
        lines = content.splitlines()
        in_socket_proxy = False
        has_socket_mount = False
        for line in lines:
            if "socket-proxy:" in line and not line.strip().startswith("#"):
                in_socket_proxy = True
            elif in_socket_proxy and line and not line.startswith(" ") and not line.startswith("\t"):
                in_socket_proxy = False
            elif in_socket_proxy and "/var/run/docker.sock" in line:
                has_socket_mount = True
        assert has_socket_mount


@pytest.mark.unit
class TestTelegramServiceSecurity:
    def test_telegram_does_not_mount_docker_socket(self):
        content = read_compose()
        lines = content.splitlines()
        in_telegram = False
        in_volumes = False
        for i, line in enumerate(lines):
            if line.strip() == "telegram:":
                in_telegram = True
            elif in_telegram and line and not line[0].isspace():
                in_telegram = False
                in_volumes = False
            elif in_telegram and "volumes:" in line:
                in_volumes = True
            elif in_telegram and in_volumes:
                if "/var/run/docker.sock" in line:
                    pytest.fail(
                        "telegram service still mounts /var/run/docker.sock directly"
                    )
                if line and not line[0].isspace():
                    in_volumes = False

    def test_telegram_has_docker_host_env(self):
        content = read_compose()
        lines = content.splitlines()
        in_telegram = False
        in_env = False
        found_docker_host = False
        for line in lines:
            if line.strip() == "telegram:":
                in_telegram = True
            elif in_telegram and line and not line[0].isspace():
                in_telegram = False
                in_env = False
            elif in_telegram and "environment:" in line:
                in_env = True
            elif in_telegram and in_env:
                if "DOCKER_HOST" in line:
                    found_docker_host = True
                if line and not line[0].isspace():
                    in_env = False
        assert found_docker_host, "telegram service missing DOCKER_HOST env var"

    def test_telegram_mounts_secrets_readonly(self):
        content = read_compose()
        lines = content.splitlines()
        in_telegram = False
        in_volumes = False
        found_secrets_mount = False
        for line in lines:
            if line.strip() == "telegram:":
                in_telegram = True
            elif in_telegram and line and not line[0].isspace():
                in_telegram = False
                in_volumes = False
            elif in_telegram and "volumes:" in line:
                in_volumes = True
            elif in_telegram and in_volumes:
                if "/opt/boardgames-secrets" in line and ":ro" in line:
                    found_secrets_mount = True
                if line and not line[0].isspace():
                    in_volumes = False
        assert found_secrets_mount, (
            "telegram service missing read-only mount for /opt/boardgames-secrets"
        )


@pytest.mark.unit
class TestRunnerServiceSecurity:
    def test_runner_does_not_mount_docker_socket(self):
        content = read_compose()
        lines = content.splitlines()
        in_runner = False
        in_volumes = False
        for i, line in enumerate(lines):
            if line.strip() == "runner:":
                in_runner = True
            elif in_runner and line and not line[0].isspace():
                in_runner = False
                in_volumes = False
            elif in_runner and "volumes:" in line:
                in_volumes = True
            elif in_runner and in_volumes:
                if "/var/run/docker.sock" in line:
                    pytest.fail(
                        "runner service still mounts /var/run/docker.sock directly"
                    )
                if line and not line[0].isspace():
                    in_volumes = False

    def test_runner_has_docker_host_env(self):
        content = read_compose()
        lines = content.splitlines()
        in_runner = False
        in_env = False
        found_docker_host = False
        for line in lines:
            if line.strip() == "runner:":
                in_runner = True
            elif in_runner and line and not line[0].isspace():
                in_runner = False
                in_env = False
            elif in_runner and "environment:" in line:
                in_env = True
            elif in_runner and in_env:
                if "DOCKER_HOST" in line:
                    found_docker_host = True
                if line and not line[0].isspace():
                    in_env = False
        assert found_docker_host, "runner service missing DOCKER_HOST env var"


@pytest.mark.unit
class TestEnvFilePaths:
    def test_env_file_uses_secrets_directory(self):
        content = read_compose()
        lines = content.splitlines()
        env_file_paths = []
        in_env_file = False
        for line in lines:
            stripped = line.strip()
            if stripped == "env_file:":
                in_env_file = True
                continue
            if in_env_file:
                if line and line[0].isspace() and stripped.startswith("- "):
                    env_file_paths.append(stripped)
                else:
                    in_env_file = False

        assert len(env_file_paths) > 0, "No env_file entries found"
        for path in env_file_paths:
            assert "/opt/boardgames-secrets/" in path, (
                f"env_file path not in /opt/boardgames-secrets/: {path}"
            )

    def test_no_relative_env_file_references(self):
        content = read_compose()
        lines = content.splitlines()
        in_env_file = False
        for line in lines:
            stripped = line.strip()
            if stripped == "env_file:":
                in_env_file = True
                continue
            if in_env_file:
                if line and line[0].isspace() and stripped.startswith("- "):
                    if stripped == "- .env" or stripped == "- .env.staging":
                        pytest.fail(
                            f"Found relative env_file reference that should use "
                            f"/opt/boardgames-secrets/: {stripped}"
                        )
                else:
                    in_env_file = False
