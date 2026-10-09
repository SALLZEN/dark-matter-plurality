#!/usr/bin/env Rscript

# PNAS Nexus manuscript-asset renderer.
#
# Main graphical elements:
#   Figures 1--3: rendered by the inspectable stepwise companion
#     006a-build-paper-assets-stepwise.R
#   Figure 4: candidate-specific paths to dark-matter closure
#
# Supporting information:
#   Figures S1--S4: rendered by the inspectable stepwise companion
#     006b-build-si-assets-stepwise.R

suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(ggplot2)
  library(jsonlite)
  library(khroma)
  library(patchwork)
  library(scales)
  library(stringr)
  library(tidyr)
})

options(stringsAsFactors = FALSE)

detect_script_dir <- function() {
  script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(script_arg)) {
    script_path <- sub("^--file=", "", script_arg[[1]])
    return(dirname(normalizePath(script_path, winslash = "/", mustWork = TRUE)))
  }

  source_path <- sys.frames()[[1]]$ofile
  if (!is.null(source_path) && length(source_path) == 1L && nzchar(source_path)) {
    return(dirname(normalizePath(source_path, winslash = "/", mustWork = TRUE)))
  }

  interactive_candidates <- c(
    file.path(getwd(), "006-build-paper-assets.R"),
    file.path(getwd(), "code", "006-build-paper-assets.R")
  )
  matching_script <- interactive_candidates[file.exists(interactive_candidates)]
  if (length(matching_script)) {
    return(dirname(normalizePath(matching_script[[1]], winslash = "/", mustWork = TRUE)))
  }

  stop(
    "Could not locate 006-build-paper-assets.R. Run it with Rscript, source it, ",
    "or set the working directory to the repository root or code/ directory."
  )
}

SCRIPT_DIR <- detect_script_dir()
WORKSPACE_ROOT <- normalizePath(file.path(SCRIPT_DIR, ".."), mustWork = TRUE)
DATA_DIR <- file.path(WORKSPACE_ROOT, "data")
ANALYSIS_DIR <- file.path(DATA_DIR, "analysis")
VALIDATION_DIR <- file.path(DATA_DIR, "validation")
FIG_DIR <- file.path(WORKSPACE_ROOT, "figures")
TABLE_DIR <- file.path(WORKSPACE_ROOT, "tables")

dir.create(FIG_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(TABLE_DIR, recursive = TRUE, showWarnings = FALSE)

ASTRO <- "astrophysics"
HEP <- "high-energy physics"
FIELD_LABELS <- c(
  "astrophysics" = "Astrophysics",
  "high-energy physics" = "High-energy physics"
)
FIELD_COLORS <- c(
  "astrophysics" = "#2166AC",
  "high-energy physics" = "#B24A33"
)
NEUTRAL <- "#4A4A4A"
GRID <- "#D9D9D9"
REPORT_FONT <- "STIX Two Text"
STIX_MATCHES <- systemfonts::match_fonts(c(REPORT_FONT, REPORT_FONT), italic = c(FALSE, TRUE))
STIX_REGULAR <- STIX_MATCHES$path[[1]]
STIX_ITALIC <- STIX_MATCHES$path[[2]]

if (!nzchar(STIX_REGULAR) || !file.exists(STIX_REGULAR) || !nzchar(STIX_ITALIC) || !file.exists(STIX_ITALIC)) {
  stop("Install STIX Two Text before rendering manuscript figures")
}
sysfonts::font_add(
  family = REPORT_FONT,
  regular = STIX_REGULAR,
  bold = STIX_REGULAR,
  italic = STIX_ITALIC,
  bolditalic = STIX_ITALIC
)
showtext::showtext_auto()

theme_report <- function(base_size = 8) {
  theme_minimal(base_size = base_size, base_family = REPORT_FONT) +
    theme(
      plot.title = element_text(face = "bold", size = rel(1.05), margin = margin(b = 5)),
      plot.subtitle = element_text(color = NEUTRAL, size = rel(0.88), margin = margin(b = 7)),
      plot.caption = element_text(color = NEUTRAL, size = rel(0.72), hjust = 0),
      axis.title = element_text(face = "plain"),
      #panel.grid.minor = element_blank(),
      #panel.grid.major = element_line(color = GRID, linewidth = 0.25),
      strip.text = element_text(face = "bold"),
      legend.title = element_text(face = "bold"),
      legend.key.height = grid::unit(3.2, "mm"),
      plot.margin = margin(5, 6, 5, 5)
    )
}

theme_nature <- function(base_size = 7) {
  theme_light(base_size = base_size, base_family = REPORT_FONT) +
    theme(
      panel.grid = element_blank(),
      panel.background = element_rect(fill = "white", color = NA),
      plot.background = element_rect(fill = "white", color = NA),
      text = element_text(family = REPORT_FONT, color = "black", size = base_size),
      axis.text = element_text(color = "black", size = base_size - 1),
      axis.title = element_text(color = "black", size = base_size),
      axis.ticks = element_line(color = "black", linewidth = 0.3),
      legend.text = element_text(color = "black", size = base_size - 1),
      legend.title = element_text(color = "black", size = base_size),
      legend.key = element_rect(fill = NA, color = NA),
      legend.margin = margin(2, 2, 2, 2),
      plot.title = element_text(color = "black", size = base_size, hjust = 0.5),
      plot.subtitle = element_text(color = "black", size = base_size - 1, hjust = 0.5),
      plot.tag = element_text(color = "black", size = 8, face = "bold")
    )
}

save_pdf <- function(plot, filename, width_mm = 180, height_mm = 110) {
  path <- file.path(FIG_DIR, filename)
  ggsave(
    path,
    plot = plot,
    width = width_mm,
    height = height_mm,
    units = "mm",
    device = grDevices::pdf,
    useDingbats = FALSE
  )
  message("Wrote ", path)
  invisible(path)
}

read_analysis <- function(stem) {
  path <- file.path(ANALYSIS_DIR, paste0(stem, ".parquet"))
  if (!file.exists(path)) stop("Missing analysis product: ", path)
  read_parquet(path)
}

require_columns <- function(data, columns, label) {
  missing <- setdiff(columns, names(data))
  if (length(missing)) stop(label, " is missing columns: ", paste(missing, collapse = ", "))
}

manifest_path <- file.path(DATA_DIR, "analysis_manifest.json")
if (!file.exists(manifest_path)) stop("Run 2.5.0-build-robustness-analysis.ipynb before rendering figures")
manifest <- fromJSON(manifest_path)
if (!identical(as.integer(manifest$analysis_cutoff_year), 2025L)) stop("Analysis manifest must end in 2025")
if (!identical(manifest$`2025_status`, "complete")) stop("Analysis manifest must mark 2025 complete")

volume <- read_analysis("paper_volume_yearly")
primary <- read_analysis("classification_primary_yearly")
assignments <- read_analysis("classification_assignment_yearly")
crosslisting <- read_analysis("classification_crosslisting_yearly")
candidate_field <- read_analysis("candidate_field_yearly")
candidate_divergence <- read_analysis("candidate_divergence_yearly")
lexical_divergence <- read_analysis("lexical_divergence_yearly")
candidates <- read_parquet(file.path(DATA_DIR, "dm_model_candidates_long.parquet"))
unigrams <- read_parquet(file.path(DATA_DIR, "unigram_yearly.parquet"))
tracked_species <- readLines(file.path(ANALYSIS_DIR, "tracked_candidate_species.txt"))

require_columns(primary, c("year", "arxiv_class", "share"), "classification_primary_yearly")
require_columns(
  candidate_divergence,
  c(
    "year", "js_divergence", "js_low", "js_high",
    "total_variation", "cosine_distance", "n_astro_papers", "n_hep_papers"
  ),
  "candidate_divergence_yearly"
)

plot_figure_1 <- function() {
  top_classes <- primary |>
    filter(year >= 2010, year <= 2025) |>
    group_by(arxiv_class) |>
    summarise(total = sum(n_papers), .groups = "drop") |>
    slice_max(total, n = 7, with_ties = FALSE) |>
    pull(arxiv_class)
  class_colors <- setNames(
    c("#2166AC", "#B24A33", "#6B6B6B", "#8A8A8A", "#A0A0A0", "#B7B7B7", "#CCCCCC"),
    c("astro-ph.CO", "hep-ph", setdiff(top_classes, c("astro-ph.CO", "hep-ph")))
  )
  class_plot <- primary |>
    filter(year >= 2010, year <= 2025, arxiv_class %in% top_classes) |>
    ggplot(aes(year, n_papers, color = arxiv_class, group = arxiv_class)) +
    geom_line(linewidth = 0.65) +
    geom_point(data = ~ filter(.x, year %in% c(2010, 2015, 2020, 2025)), size = 0.9) +
    scale_color_manual(values = class_colors) +
    scale_x_continuous(breaks = c(2010, 2015, 2020, 2025)) +
    scale_y_sqrt(
      breaks = c(100, 500, 1000, 2000, 3000),
      labels = label_number(scale_cut = cut_short_scale())
    ) +
    labs(
      title = "Leading primary arXiv classes",
      subtitle = "Annual paper counts; square-root scale",
      x = NULL, y = "Papers per year", color = "Primary class"
    ) +
    theme_report() +
    guides(color = guide_legend(ncol = 2, byrow = TRUE)) +
    theme(
      legend.position = "bottom",
      legend.direction = "horizontal",
      legend.text = element_text(size = 5.2),
      legend.key.width = grid::unit(3.5, "mm")
    )

  broad_primary <- assignments |>
    filter(
      year >= 2010, year <= 2025,
      assignment == "primary",
      arxiv_category %in% names(FIELD_LABELS)
    ) |>
    mutate(
      field = recode(arxiv_category, !!!FIELD_LABELS)
    )
  broad_labels <- broad_primary |>
    filter(year == 2025) |>
    mutate(label = paste0(field, " ", percent(share, accuracy = 0.1)))
  broad_plot <- broad_primary |>
    ggplot(aes(year, share, color = arxiv_category)) +
    geom_line(linewidth = 0.8) +
    geom_point(data = broad_labels, size = 1.4) +
    geom_text(
      data = broad_labels, aes(label = label),
      hjust = 1.05, size = 2.35, show.legend = FALSE
    ) +
    scale_color_manual(values = FIELD_COLORS, labels = FIELD_LABELS) +
    scale_x_continuous(breaks = c(2010, 2015, 2020, 2025), limits = c(2010, 2025)) +
    scale_y_continuous(labels = label_percent(accuracy = 1)) +
    labs(
      title = "Astrophysics remains the larger broad field",
      subtitle = "Primary-class assignment",
      x = NULL, y = "Share of classified papers", color = NULL
    ) +
    theme_report() +
    theme(legend.position = "none")

  figure <- (broad_plot | class_plot) +
    plot_annotation(tag_levels = "A") &
    theme(plot.tag = element_text(face = "bold", size = 10))
  save_pdf(figure, "primary_dominant.pdf", 180, 86)
}

plot_figure_2 <- function() {
  species_order <- candidate_field |>
    filter(meets_minimum_count) |>
    group_by(SpeciesLabel) |>
    summarise(median_ratio = median(log2_hep_astro_ratio, na.rm = TRUE), .groups = "drop") |>
    arrange(desc(median_ratio)) |>
    pull(SpeciesLabel)

  plot_data <- candidate_field |>
    filter(SpeciesLabel %in% species_order) |>
    mutate(
      SpeciesLabel = factor(SpeciesLabel, levels = rev(species_order)),
      shown_ratio = if_else(meets_minimum_count, log2_hep_astro_ratio, NA_real_)
    )
  heatmap <- ggplot(plot_data, aes(year, SpeciesLabel, fill = shown_ratio)) +
    geom_tile(color = "white", linewidth = 0.12) +
    scale_fill_gradient2(
      low = "#2166AC", mid = "#F7F7F7", high = "#B2182B", midpoint = 0,
      limits = c(-4, 4), oob = squish, na.value = "white",
      name = expression(log[2]~"HEP/astro share")
    ) +
    scale_x_continuous(breaks = seq(1995, 2025, 5), expand = c(0, 0)) +
    labs(
      title = "Candidate attention differs by field",
      subtitle = "Blank cells contain fewer than 20 paper-candidate mentions.",
      x = NULL, y = NULL,
      caption = "Blue indicates greater astrophysics share; red indicates greater HEP share. A paper may mention more than one candidate."
    ) +
    theme_report(7.5) +
    theme(
      panel.grid = element_blank(),
      legend.position = "bottom",
      axis.text.y = element_text(size = 6.5)
    )
  save_pdf(heatmap, "log_ratio.pdf", 180, 105)
}

candidate_composition <- function() {
  candidates |>
    filter(
      year >= 1995, year <= 2025,
      arxiv_category %in% names(FIELD_LABELS),
      SpeciesLabel %in% tracked_species
    ) |>
    distinct(year, arxiv_category, bibcode, SpeciesLabel) |>
    count(year, arxiv_category, SpeciesLabel, name = "n") |>
    group_by(year, arxiv_category) |>
    mutate(share = n / sum(n)) |>
    ungroup() |>
    mutate(
      field = recode(arxiv_category, !!!FIELD_LABELS),
      SpeciesLabel = factor(SpeciesLabel, levels = tracked_species)
    )
}

plot_figure_3 <- function() {
  composition <- candidate_composition()
  colors <- setNames(khroma::color("batlow", type = "qualitative", reverse = TRUE)(length(tracked_species)), tracked_species)
  areas <- ggplot(composition, aes(year, share, fill = SpeciesLabel)) +
    geom_area(color = "white", linewidth = 0.08) +
    facet_wrap(~ field, nrow = 1) +
    scale_fill_manual(values = colors, drop = FALSE) +
    scale_x_continuous(breaks = seq(1995, 2025, 5)) +
    scale_y_continuous(labels = label_percent(accuracy = 1), expand = c(0, 0)) +
    labs(
      title = "Candidate composition follows different field-specific trajectories",
      subtitle = "Shares are normalized within each field-year; a paper may mention more than one candidate.",
      x = NULL, y = "Share of paper-candidate-family mentions", fill = "Candidate"
    ) +
    theme_report(7.5) +
    theme(legend.position = "right", legend.text = element_text(size = 5.6), legend.key.height = grid::unit(2.6, "mm"))

  save_pdf(areas, "norm.pdf", 180, 92)
}

plot_figure_4 <- function() {
  closure <- tribble(
    ~result, ~condition, ~assessment, ~detail,
    "Laboratory axion/ALP signal", "Constitutive identification", "Potentially", "New particle or field identified",
    "Laboratory axion/ALP signal", "Cosmic attribution", "Not by itself", "Abundance and distribution remain open",
    "Laboratory axion/ALP signal", "Explanatory adequacy", "Not by itself", "Cosmic explanatory reach remains open",
    "Laboratory axion/ALP signal", "Cross-domain identification", "Not by itself", "Signal must be linked to cosmic component",
    "WIMP recoil with convergent evidence", "Constitutive identification", "Potentially", "Requires robust signal interpretation",
    "WIMP recoil with convergent evidence", "Cosmic attribution", "Potentially", "Requires halo and cosmological inference",
    "WIMP recoil with convergent evidence", "Explanatory adequacy", "Potentially", "Could account for attributed phenomena",
    "WIMP recoil with convergent evidence", "Cross-domain identification", "Potentially", "Convergence could connect all evidence",
    "Cosmologically significant PBH population", "Constitutive identification", "Potentially", "Population identified categorically",
    "Cosmologically significant PBH population", "Cosmic attribution", "Potentially", "Population and abundance constrained",
    "Cosmologically significant PBH population", "Explanatory adequacy", "Potentially", "Could account for gravitational evidence",
    "Cosmologically significant PBH population", "Cross-domain identification", "Potentially", "Same population must close the roles",
    "Modified-gravity success", "Constitutive identification", "No component", "No dark constituent identified",
    "Modified-gravity success", "Cosmic attribution", "No component", "No dark constituent attributed",
    "Modified-gravity success", "Explanatory adequacy", "Potentially", "May explain attributed phenomena",
    "Modified-gravity success", "Cross-domain identification", "No component", "Resolves or dissolves the composition claim"
  ) |>
    mutate(
      result = recode(
        result,
        "Laboratory axion/ALP signal" = "Laboratory\naxion/ALP signal",
        "WIMP recoil with convergent evidence" = "WIMP recoil with\nconvergent evidence",
        "Cosmologically significant PBH population" = "Cosmologically significant\nPBH population"
      ),
      result = factor(result, levels = rev(c(
        "Laboratory\naxion/ALP signal",
        "WIMP recoil with\nconvergent evidence",
        "Cosmologically significant\nPBH population",
        "Modified-gravity success"
      ))),
      condition = factor(condition, levels = c(
        "Constitutive identification", "Cosmic attribution",
        "Explanatory adequacy", "Cross-domain identification"
      )),
      detail = str_wrap(detail, 22)
    )
  fills <- c("Potentially" = "#D7E8D2", "Not by itself" = "#F3E2B8", "No component" = "#E2E2E2")
  matrix_plot <- ggplot(closure, aes(condition, result, fill = assessment)) +
    geom_tile(color = "white", linewidth = 1.2) +
    geom_text(aes(label = assessment), fontface = "bold", size = 2.25, nudge_y = 0.13, color = "#222222") +
    geom_text(aes(label = detail), size = 1.85, lineheight = 0.88, nudge_y = -0.14, color = "#222222") +
    scale_fill_manual(values = fills, guide = "none") +
    scale_x_discrete(labels = function(x) str_wrap(x, 16), position = "top") +
    labs(
      title = "Candidate-specific paths to dark-matter closure",
      subtitle = "A strong discovery claim requires I(c), A(c), E(c), and cross-domain identification L(c).",
      x = NULL, y = NULL,
      caption = "Assessments indicate what each stipulated result could establish; they are not claims about candidate viability."
    ) +
    theme_report(8) +
    theme(
      panel.grid = element_blank(),
      axis.text.x = element_text(face = "bold", size = 6.9, lineheight = 0.88),
      axis.text.y = element_text(face = "bold", size = 6.8, lineheight = 0.88),
      axis.ticks = element_blank(),
      plot.margin = margin(5, 7, 5, 5)
    )
  save_pdf(matrix_plot, "fig4_closure_conditions.pdf", 180, 99)
}

write_candidate_table <- function() {
  totals <- candidates |>
    filter(year >= 1995, year <= 2025, arxiv_category %in% names(FIELD_LABELS), SpeciesLabel %in% tracked_species) |>
    distinct(arxiv_category, bibcode, SpeciesLabel) |>
    count(arxiv_category, SpeciesLabel, name = "mentions") |>
    group_by(arxiv_category) |>
    arrange(desc(mentions), .by_group = TRUE) |>
    slice_head(n = 12) |>
    mutate(rank = row_number()) |>
    ungroup() |>
    select(rank, arxiv_category, SpeciesLabel, mentions) |>
    pivot_wider(names_from = arxiv_category, values_from = c(SpeciesLabel, mentions))

  path <- file.path(TABLE_DIR, "tableS1_candidate_terms.tex")
  con <- file(path, open = "wt")
  writeLines(c(
    "\\begin{tabular}{l r l r}",
    "\\toprule",
    "\\multicolumn{2}{c}{Astrophysics} & \\multicolumn{2}{c}{High-energy physics} \\\\",
    "Candidate & Mentions & Candidate & Mentions \\\\",
    "\\midrule"
  ), con)
  for (i in seq_len(nrow(totals))) {
    writeLines(sprintf(
      "%s & %s & %s & %s \\\\",
      totals$SpeciesLabel_astrophysics[[i]], comma(totals$mentions_astrophysics[[i]]),
      totals$`SpeciesLabel_high-energy physics`[[i]], comma(totals$`mentions_high-energy physics`[[i]])
    ), con)
  }
  writeLines(c("\\bottomrule", "\\end{tabular}"), con)
  close(con)
}

write_alt_text <- function() {
  alt <- c(
    "# Figure alt text",
    "",
    "## Figure 1",
    "Two-panel time-series figure. The left panel aggregates primary classes and shows that astrophysics remains substantially larger than high-energy physics through 2025. The right panel shows annual counts for the seven primary arXiv classes with the largest cumulative counts in 2010-2025 on a square-root scale; hep-ph first exceeds astro-ph.CO in 2015, while the ordering varies thereafter. A strip identifies the leading displayed class each year and its share across those seven classes.",
    "",
    "## Figure 2",
    "Heat map of candidate share ratios from 1995 through 2025. Supersymmetry-related candidates are generally more prominent in high-energy physics, while primordial black holes, MACHOs, and ultralight or fuzzy candidates are more prominent in astrophysics. Blank cells have fewer than 20 mentions across the two fields.",
    "",
    "## Figure 3",
    "Two stacked area panels show normalized candidate composition in astrophysics and high-energy physics from 1995 through 2025. WIMP-related candidates lose share, while axion and ALP work expands especially in high-energy physics and primordial-black-hole work expands especially in astrophysics.",
    "",
    "## Figure 4",
    "Four-column matrix comparing four possible dark-matter results across constitutive identification, cosmic attribution, explanatory adequacy, and cross-domain identification. A WIMP result could potentially connect all four through convergent evidence. A laboratory axion or ALP signal, a cosmologically significant primordial-black-hole population, and modified-gravity success close different profiles of conditions; no condition follows automatically from another.",
    "",
    "## Figure S1",
    "Three-part classification sensitivity figure. Publication volume rises strongly after 1990; broad-field shares remain larger for astrophysics under primary, any-class, and fractional assignments; and approximately 17 to 20 percent of classified papers are cross-listed between astrophysics and high-energy physics.",
    "",
    "## Figure S2",
    "Two stacked area charts show raw annual paper-candidate-family mentions in astrophysics and high-energy physics. Counts grow strongly over time and are displayed on separate vertical scales.",
    "",
    "## Figure S3",
    "Three-part candidate-distance figure. Jensen-Shannon divergence is shown with a paper-bootstrap interval; total-variation and cosine distances provide alternative summaries; and a log-scale sample-size panel shows that early annual estimates rely on substantially fewer candidate-mentioning papers.",
    "",
    "## Figure S4",
    "A top line plot shows vocabulary divergence with all eligible unigrams and with the 16 predefined candidate-name unigrams removed. Lower small multiples show the five strongest data-selected rising and five strongest declining term trajectories in each field after the documented exclusions and minimum-frequency thresholds."
  )
  path <- file.path(FIG_DIR, "alt_text.md")
  writeLines(alt, path)

  figure_manifest <- list(
    schema_version = 1,
    renderer = "R/ggplot2 vector PDF",
    cutoff_year = 2025,
    figures = list(
      list(file = "primary_dominant.pdf", data = c("classification_primary_yearly", "classification_assignment_yearly")),
      list(file = "log_ratio.pdf", data = c("candidate_field_yearly")),
      list(file = "norm.pdf", data = c("dm_model_candidates_long")),
      list(file = "fig4_closure_conditions.pdf", data = c("schematic synthesis")),
      list(file = "figS1_classification_sensitivity.pdf", data = c("paper_volume_yearly", "classification_assignment_yearly", "classification_crosslisting_yearly")),
      list(file = "figS2_candidate_raw_counts.pdf", data = c("dm_model_candidates_long")),
      list(file = "figS3_candidate_distances.pdf", data = c("candidate_divergence_yearly")),
      list(file = "figS4_lexical_divergence.pdf", data = c("lexical_divergence_yearly", "unigram_yearly"))
    )
  )
  manifest_output <- file.path(FIG_DIR, "figure_manifest.json")
  write_json(figure_manifest, manifest_output, pretty = TRUE, auto_unbox = TRUE)
}

render_stepwise_main_figures <- function() {
  stepwise_path <- file.path(SCRIPT_DIR, "006a-build-paper-assets-stepwise.R")
  if (!file.exists(stepwise_path)) stop("Missing stepwise main-figure renderer: ", stepwise_path)

  old_workspace <- Sys.getenv("PNAS_WORKSPACE_ROOT", unset = NA_character_)
  old_output <- Sys.getenv("PNAS_FIGURE_OUTPUT_DIR", unset = NA_character_)
  on.exit({
    if (is.na(old_workspace)) Sys.unsetenv("PNAS_WORKSPACE_ROOT") else Sys.setenv(PNAS_WORKSPACE_ROOT = old_workspace)
    if (is.na(old_output)) Sys.unsetenv("PNAS_FIGURE_OUTPUT_DIR") else Sys.setenv(PNAS_FIGURE_OUTPUT_DIR = old_output)
  }, add = TRUE)

  Sys.setenv(
    PNAS_WORKSPACE_ROOT = WORKSPACE_ROOT,
    PNAS_FIGURE_OUTPUT_DIR = FIG_DIR
  )
  sys.source(stepwise_path, envir = new.env(parent = globalenv()))
}

render_stepwise_si_figures <- function() {
  stepwise_path <- file.path(SCRIPT_DIR, "006b-build-si-assets-stepwise.R")
  if (!file.exists(stepwise_path)) stop("Missing stepwise SI-figure renderer: ", stepwise_path)

  old_workspace <- Sys.getenv("PNAS_WORKSPACE_ROOT", unset = NA_character_)
  old_output <- Sys.getenv("PNAS_FIGURE_OUTPUT_DIR", unset = NA_character_)
  on.exit({
    if (is.na(old_workspace)) Sys.unsetenv("PNAS_WORKSPACE_ROOT") else Sys.setenv(PNAS_WORKSPACE_ROOT = old_workspace)
    if (is.na(old_output)) Sys.unsetenv("PNAS_FIGURE_OUTPUT_DIR") else Sys.setenv(PNAS_FIGURE_OUTPUT_DIR = old_output)
  }, add = TRUE)

  Sys.setenv(
    PNAS_WORKSPACE_ROOT = WORKSPACE_ROOT,
    PNAS_FIGURE_OUTPUT_DIR = FIG_DIR
  )
  sys.source(stepwise_path, envir = new.env(parent = globalenv()))
}

main <- function() {
  render_stepwise_main_figures()
  plot_figure_4()
  render_stepwise_si_figures()
  write_candidate_table()
  write_alt_text()
  message("PNAS Nexus manuscript assets are complete.")
}

main()
