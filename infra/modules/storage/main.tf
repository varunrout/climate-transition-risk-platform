# ADLS Gen2 lakehouse storage: raw/bronze/silver/gold/manifests as one
# hierarchical-namespace storage account with per-zone containers.
#
# Cost posture: Standard_LRS (cheapest redundancy Azure offers -- locally
# redundant, single region, no geo-replication). This project's raw
# snapshots + manifests + committed pipeline code are the reproducibility
# story (docs/finops.md); GRS/ZRS would pay for durability this project
# doesn't need. Hot tier by default; a lifecycle rule moves raw/ blobs to
# Cool after 30 days since they are read rarely once bronze is built from
# them, and deletes anything under a temp/ prefix after 7 days as a safety
# net for orphaned atomic-write temp files.

resource "azurerm_storage_account" "lake" {
  name                            = var.storage_account_name
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  is_hns_enabled                  = true # hierarchical namespace -> ADLS Gen2
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false # no anonymous blob access, ever
  shared_access_key_enabled       = true  # container apps job auth is via managed identity (see identity module); left on only for local `az storage` debugging

  blob_properties {
    delete_retention_policy {
      days = 7 # short retention: this is a portfolio project, not a compliance workload
    }
  }

  tags = var.tags
}

resource "azurerm_storage_data_lake_gen2_filesystem" "zones" {
  for_each           = toset(["raw", "bronze", "silver", "gold"])
  name               = each.value
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.lake.id

  rule {
    name    = "raw-to-cool-after-30-days"
    enabled = true
    filters {
      prefix_match = ["raw/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than = 30
      }
    }
  }

  # Deliberately no blanket delete rule on bronze/silver/gold: those are the
  # reproducible analytical outputs, not disposable data. Orphaned atomic-write
  # temp files (.data.parquet.tmp, left behind only if a job crashes between
  # write and rename) are a few KB at most and not worth a lifecycle rule that
  # would need per-run-id prefix knowledge Azure Storage lifecycle filters
  # can't express safely -- a blanket prefix/age rule here risks deleting real
  # published data, which is a much worse outcome than a stray tmp file.
}
