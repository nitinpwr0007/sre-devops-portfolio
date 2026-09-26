# tflint config. The "terraform" ruleset is BUILT-IN (bundled with tflint), so
# no `tflint --init` / plugin download is needed — important behind the proxy.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
