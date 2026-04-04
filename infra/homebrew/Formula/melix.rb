class Melix < Formula
  desc "Local-first AI runtime for Apple Silicon"
  homepage "https://github.com/Keith-CY/melix"

  repo_root = Pathname.new(__FILE__).realpath.parent.parent.parent
  url "file://#{repo_root}"
  version "0.1.0"
  sha256 :no_check

  depends_on "python@3.12"
  depends_on "uv"

  def install
    libexec.install Dir["*"]

    system "swift", "build", "-c", "release", "--package-path", libexec, "--product", "melix"
    system "swift", "build", "-c", "release", "--package-path", libexec/"services/control-plane-swift", "--product", "melix-control-plane"
    system "swift", "build", "-c", "release", "--package-path", libexec/"services/mlx-text-worker-swift", "--product", "melix-text-worker-swift"

    bin.install libexec/".build/release/melix"
    bin.install libexec/"services/control-plane-swift/.build/release/melix-control-plane"
    bin.install libexec/"services/mlx-text-worker-swift/.build/release/melix-text-worker-swift"
    (bin/"melix-homebrew-service").write_env_script(
      libexec/"scripts/melix_homebrew_service.py",
      {
        "MELIX_REPO_ROOT" => libexec,
        "MELIX_HOMEBREW_BIN_DIR" => bin,
        "PYTHONPATH" => "#{libexec}:#{libexec}/services/mlx-worker-python",
      }
    )
  end

  service do
    run [opt_bin/"melix-homebrew-service", "run"]
    keep_alive true
    working_dir var/"melix"
    log_path var/"log/melix/homebrew-service.log"
    error_log_path var/"log/melix/homebrew-service.err.log"
  end

  test do
    output = shell_output("#{bin}/melix-homebrew-service manifest --json")
    assert_match "io.melix.homebrew.control-plane", output
  end
end
