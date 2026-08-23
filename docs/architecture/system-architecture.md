# System architecture

Three complementary views: what data flows through (system), what runs
where in Azure (deployment), and how raw numbers become a published risk
score (analytical flow). Diagrams are Mermaid so they stay in Git as text
and render on GitHub.

## A. System architecture

```mermaid
flowchart LR
    subgraph sources["Public sources"]
        owid_co2["OWID CO2"]
        wdi["World Bank WDI"]
        owid_energy["OWID Energy"]
    end

    sources -->|ingestion adapters| raw["raw/\ncontent-hashed, never overwritten"]
    raw -->|dedupe, normalise| bronze["bronze/\nper-source curated tables"]
    bronze -->|dimension model,\nunit normalisation| silver["silver/\ncountry-year panel"]
    silver --> analytics["analytics\n(features, scoring, scenarios,\nbacktesting)"]
    analytics -->|fail-closed publish| gold["gold/\nversioned analytical release"]
    gold -->|build-bi| goldbi["gold/bi/\nBI-shaped tables"]
    goldbi -->|build-web| goldweb["gold/web/\nchecksummed JSON bundle"]
    goldweb --> api["Read-only FastAPI"]
    goldweb --> web["React dashboard"]
```

## B. Deployment architecture

```mermaid
flowchart LR
    dev["git push"] --> gh["GitHub"]
    gh --> gha["GitHub Actions"]
    gha -->|build-containers.yml| ghcr["GHCR\n(public, immutable Git-SHA tags)"]
    gha -->|deploy-web.yml| pages["GitHub Pages\n(React dashboard, static)"]
    ghcr --> job["Azure Container Apps Job\n(scheduled, Monday 03:00 UTC)"]
    ghcr --> capi["Azure Container App\n(API, scale-to-zero, max 1 replica)"]

    job -->|id-climate-risk-job\nStorage Blob Data Contributor| adls["Azure Data Lake\nStorage Gen2"]
    capi -->|id-climate-risk-api\nStorage Blob Data Reader ONLY| adls

    job -.->|structured logs| loganalytics["Log Analytics\n0.1GB/day cap"]
    capi -.->|structured logs| loganalytics

    subgraph identity["No keys / SAS / connection strings anywhere"]
        job
        capi
    end
```

## C. Analytical flow

```mermaid
flowchart TD
    source_data["source data\n(silver panel)"] --> features["features\n(decoupling, energy-transition\nindicators)"]
    features --> evidence["evidence / backtesting\n(rolling-origin, baseline comparison,\nweight-perturbation robustness)"]
    evidence --> scoring["score / scenario\nv2_energy + empirical_bootstrap_v1\n(v1 retained as comparison)"]
    scoring -->|fail-closed barrier| publish["publish\n(core analytical release)"]
    publish -->|only after core succeeds| product["product publication\n(build-bi -> build-web)"]
    product --> manifest["gold/web/manifest.json\nschema version, provenance,\nper-file hashes, bundle hash"]
```

A product-publication failure (the last step) is reported loudly but never
rolls back or corrupts a valid core `publish` — the two layers fail
independently (ADR 0019).

## Notes on what this diagram deliberately omits

- **Power BI** (`powerbi/`) is preserved as engineering history — a
  superseded prototype route, not part of the canonical v1 architecture.
  See ADR 0015/0016 for why the canonical product moved to React.
- **No Azure Container Registry** — GHCR is public and free; ACR would add
  cost for no benefit here.
- **No database** — every artifact is a file in ADLS Gen2 (Parquet in
  `gold/bi`, JSON in `gold/web`); the API reads directly from storage, it
  does not run a query engine.
