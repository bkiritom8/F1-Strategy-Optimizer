/**
 * Dynamic zone selection for the Vertex AI Workbench instance.
 *
 * How it works:
 *   - In Cloud Build: scripts/find_workbench_zone.sh runs before terraform,
 *     writing the selected zone to .workbench_zone.  The data source below
 *     reads the already-written file — null_resource is a no-op in that path.
 *   - For local runs: the null_resource runs the script on first apply (or
 *     whenever the script itself changes) and writes .workbench_zone.
 *
 * .workbench_zone is git-ignored (generated file).
 */

resource "null_resource" "find_workbench_zone" {
  triggers = {
    # Re-run only when the zone-finder script changes, keeping the plan stable
    # across normal applies while still picking up script updates.
    script_hash = filemd5("${path.module}/../../scripts/find_workbench_zone.sh")
  }

  provisioner "local-exec" {
    command = "bash ${path.module}/../../scripts/find_workbench_zone.sh > ${path.module}/.workbench_zone"
  }
}

data "local_file" "workbench_zone" {
  filename   = "${path.module}/.workbench_zone"
  depends_on = [null_resource.find_workbench_zone]
}
