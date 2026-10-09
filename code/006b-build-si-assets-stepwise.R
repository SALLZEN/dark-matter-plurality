#!/usr/bin/env Rscript

# Stepwise SI companion to 006-build-paper-assets.R
#
# Purpose:
#   Reproduce Figures S1--S4 one section at a time, keep the intermediate data
#   and plot objects visible in an IDE, and make every display decision easy to
#   inspect against the frozen analysis products.
#
# Recommended use in RStudio:
#   1. Open this file and run the numbered sections in order.
#   2. Set SAVE_OUTPUTS <- FALSE before running if you only want to explore.
#   3. Inspect each named data and plot object in the Environment and plot pane.
#   4. Set SAVE_OUTPUTS <- TRUE to write the four final SI PDFs.

detect_stepwise_dir <- function() {
  script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(script_arg)) {
    script_path <- sub("^--file=", "", script_arg[[1]])
    return(dirname(normalizePath(script_path, winslash = "/", mustWork = TRUE)))
  }
  source_path <- sys.frames()[[1]]$ofile
  if (!is.null(source_path) && length(source_path) == 1L && nzchar(source_path)) {
    return(dirname(normalizePath(source_path, winslash = "/", mustWork = TRUE)))
  }
  root_launch_path <- file.path(getwd(), "code", "006b-build-si-assets-stepwise.R")
  if (file.exists(root_launch_path)) {
    return(dirname(normalizePath(root_launch_path, winslash = "/", mustWork = TRUE)))
  }
  normalizePath(getwd(), winslash = "/", mustWork = TRUE)
}

STEPWISE_DIR <- detect_stepwise_dir()

suppressWarnings(suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(ggplot2)
  library(jsonlite)
  library(khroma)
  library(patchwork)
  library(scales)
  library(stringr)
  library(tidyr)
}))

if (!exists("SAVE_OUTPUTS", inherits = FALSE)) SAVE_OUTPUTS <- TRUE

BASE_FONT <- "STIX Two Text"
REPORT_FONT <- BASE_FONT

workspace_candidates <- c(
  Sys.getenv("PNAS_WORKSPACE_ROOT", unset = ""),
  normalizePath(file.path(STEPWISE_DIR, ".."), winslash = "/", mustWork = FALSE)
)
workspace_candidates <- unique(workspace_candidates[nzchar(workspace_candidates)])
required_inputs <- c(
  file.path("data", "analysis", "paper_volume_yearly.parquet"),
  file.path("data", "analysis", "classification_assignment_yearly.parquet"),
  file.path("data", "analysis", "classification_crosslisting_yearly.parquet"),
  file.path("data", "analysis", "candidate_divergence_yearly.parquet"),
  file.path("data", "analysis", "lexical_divergence_yearly.parquet"),
  file.path("data", "analysis", "tracked_candidate_species.txt"),
  file.path("data", "dm_model_candidates_long.parquet"),
  file.path("data", "unigram_yearly.parquet"),
  file.path("data", "analysis_manifest.json")
)
workspace_has_inputs <- vapply(
  workspace_candidates,
  function(path) all(file.exists(file.path(path, required_inputs))),
  logical(1)
)

if (!any(workspace_has_inputs)) {
  stop(
    paste(
      "Could not locate the frozen SI inputs.",
      "Set PNAS_WORKSPACE_ROOT to the reproduction repository."
    ),
    call. = FALSE
  )
}

WORKSPACE_ROOT <- normalizePath(
  workspace_candidates[workspace_has_inputs][[1]],
  winslash = "/",
  mustWork = TRUE
)
DATA_DIR <- file.path(WORKSPACE_ROOT, "data")
ANALYSIS_DIR <- file.path(DATA_DIR, "analysis")
FIGURE_OUTPUT_DIR <- Sys.getenv(
  "PNAS_FIGURE_OUTPUT_DIR",
  unset = file.path(WORKSPACE_ROOT, "figures")
)

if (SAVE_OUTPUTS) {
  dir.create(FIGURE_OUTPUT_DIR, recursive = TRUE, showWarnings = FALSE)
}

font_matches <- systemfonts::match_fonts(c(REPORT_FONT, REPORT_FONT), italic = c(FALSE, TRUE))
if (!all(nzchar(font_matches$path)) || !all(file.exists(font_matches$path))) {
  stop("Install STIX Two Text before rendering SI figures", call. = FALSE)
}
sysfonts::font_add(
  family = REPORT_FONT,
  regular = font_matches$path[[1]],
  bold = font_matches$path[[1]],
  italic = font_matches$path[[2]],
  bolditalic = font_matches$path[[2]]
)
showtext::showtext_auto()

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

theme_report <- function(base_size = 8) {
  theme_minimal(base_size = base_size, base_family = REPORT_FONT) +
    theme(
      plot.title = element_text(face = "bold", size = rel(1.05), margin = margin(b = 5)),
      plot.subtitle = element_text(color = NEUTRAL, size = rel(0.88), margin = margin(b = 7)),
      plot.caption = element_text(color = NEUTRAL, size = rel(0.72), hjust = 0),
      axis.title = element_text(face = "plain"),
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

save_stepwise_pdf <- function(plot, filename, width_mm, height_mm) {
  path <- file.path(FIGURE_OUTPUT_DIR, filename)
  ggplot2::ggsave(
    filename = path,
    plot = plot,
    device = grDevices::pdf,
    width = width_mm,
    height = height_mm,
    units = "mm",
    useDingbats = FALSE
  )
  message("Wrote ", path)
  invisible(path)
}

require_columns <- function(data, columns, label) {
  missing <- setdiff(columns, names(data))
  if (length(missing)) stop(label, " is missing columns: ", paste(missing, collapse = ", "))
}

# Step 1: load and inspect the frozen SI inputs -------------------------------

manifest <- fromJSON(file.path(DATA_DIR, "analysis_manifest.json"))
if (!identical(as.integer(manifest$analysis_cutoff_year), 2025L)) {
  stop("Analysis manifest must end in 2025", call. = FALSE)
}
if (!identical(manifest$`2025_status`, "complete")) {
  stop("Analysis manifest must mark 2025 complete", call. = FALSE)
}

volume <- read_parquet(file.path(ANALYSIS_DIR, "paper_volume_yearly.parquet"))
assignments <- read_parquet(file.path(ANALYSIS_DIR, "classification_assignment_yearly.parquet"))
crosslisting <- read_parquet(file.path(ANALYSIS_DIR, "classification_crosslisting_yearly.parquet"))
candidate_divergence <- read_parquet(file.path(ANALYSIS_DIR, "candidate_divergence_yearly.parquet"))
lexical_divergence <- read_parquet(file.path(ANALYSIS_DIR, "lexical_divergence_yearly.parquet"))
candidates <- read_parquet(file.path(DATA_DIR, "dm_model_candidates_long.parquet"))
unigrams <- read_parquet(file.path(DATA_DIR, "unigram_yearly.parquet"))
tracked_species <- readLines(file.path(ANALYSIS_DIR, "tracked_candidate_species.txt"))

require_columns(volume, c("year", "n_papers"), "paper_volume_yearly")
require_columns(
  assignments,
  c("year", "assignment", "arxiv_category", "share"),
  "classification_assignment_yearly"
)
require_columns(
  crosslisting,
  c("year", "crosslisting_rate", "crosslisting_low", "crosslisting_high"),
  "classification_crosslisting_yearly"
)
require_columns(
  candidate_divergence,
  c(
    "year", "js_divergence", "js_low", "js_high", "total_variation",
    "cosine_distance", "n_astro_papers", "n_hep_papers"
  ),
  "candidate_divergence_yearly"
)
require_columns(
  lexical_divergence,
  c("year", "js_divergence", "vocabulary_scope"),
  "lexical_divergence_yearly"
)
require_columns(
  candidates,
  c("year", "arxiv_category", "bibcode", "SpeciesLabel"),
  "dm_model_candidates_long"
)
require_columns(
  unigrams,
  c("year", "field", "term", "n_kw", "n_papers", "rate"),
  "unigram_yearly"
)

message("Loaded frozen SI products from: ", WORKSPACE_ROOT)
message("  paper_volume_yearly: ", nrow(volume), " rows")
message("  classification_assignment_yearly: ", nrow(assignments), " rows")
message("  classification_crosslisting_yearly: ", nrow(crosslisting), " rows")
message("  candidate_divergence_yearly: ", nrow(candidate_divergence), " rows")
message("  lexical_divergence_yearly: ", nrow(lexical_divergence), " rows")
message("  dm_model_candidates_long: ", nrow(candidates), " rows")
message("  unigram_yearly: ", nrow(unigrams), " rows")

# Step 2: Figure S1 -- corpus and classification sensitivity -----------------


volume_plot <- volume |>
  filter(year >= 1985, year <= 2025) |>
  ggplot(aes(year, n_papers)) +
  geom_area(fill = "#B2DFDBFF",alpha = 0.95) +
  geom_line(color = "#00695CFF") +
  scale_x_continuous(
    breaks = seq(1985, 2025, 5),
    expand = expansion(mult = c(0.0, 0.02))
    ) +
  scale_y_continuous(
    labels = label_number(big.mark = ","), 
    expand = expansion(mult = c(0.025, 0.05))) +
  labs(title = "Publication volume", x = NULL, y = NULL) +
  theme_report() +
  theme(
    plot.title = element_text(
      family = REPORT_FONT,
      size = 10,
      hjust = 0.0
    ),
    plot.subtitle = element_text(
      family = REPORT_FONT,
      size = 9,
      hjust = -0.05
    )
  )

volume_plot

#"#D2FBD4FF", "#A5DBC2FF", "#7BBCB0FF", "#559C9EFF", "#3A7C89FF", "#235D72FF", "#123F5AFF"
#"#F3CBD3FF", "#EAA9BDFF", "#DD88ACFF", "#CA699DFF", "#B14D8EFF", "#91357DFF", "#6C2167FF"


hep_class_sensitivity_colors <- c(
  "fractional" = "#EAA9BDFF",
  "any class"  = "#CA699DFF",
  "primary"    = "#6C2167FF"
)

astro_class_sensitivity_colors <- c(
  "fractional" = "#A5DBC2FF",
  "any class"  = "#559C9EFF",
  "primary"    = "#123F5AFF"
)

make_assignment_panel <- function(field_key, field_title, colors, y_title = NULL) {
  assignments |>
    filter(
      year >= 2010,
      year <= 2025,
      arxiv_category == field_key
    ) |>
    mutate(
      assignment = factor(
        assignment,
        levels = c("primary", "any class", "fractional")
      )
    ) |>
    ggplot(aes(year, share, color = assignment)) +
    geom_line(linewidth = 1) +
    scale_color_manual(
      values = colors,
      breaks = c("primary", "any class", "fractional"),
      labels = c(
        "primary" = "Primary",
        "any class" = "Any class",
        "fractional" = "Fractional"
      )
    ) +
    scale_x_continuous(
      breaks = c(2010, 2015, 2020, 2025),
      expand = expansion(mult = c(0.01, 0.02))
    ) +
    scale_y_continuous(
      limits = c(0.25, 0.72),
      breaks = seq(0.30, 0.70, 0.10),
      labels = label_percent(accuracy = 1)
    ) +
    labs(
      title = field_title,
      x = NULL,
      y = y_title,
      color = NULL
    ) +
    guides(color = guide_legend(nrow = 1)) +
    theme_report() +
    theme(
      plot.title = element_text(family = REPORT_FONT, size = 7, hjust = 0.01, vjust = -0.5),
      legend.position = "bottom",
      legend.direction = "horizontal",
      legend.margin = margin(t = -5, r = 0, b = -5, l = 0)
    )
}

astro_assignment_plot <- make_assignment_panel(
  field_key = "astrophysics",
  field_title = "Astrophysics",
  colors = astro_class_sensitivity_colors,
  y_title = NULL
)

hep_assignment_plot <- make_assignment_panel(
  field_key = "high-energy physics",
  field_title = "High-energy physics",
  colors = hep_class_sensitivity_colors
)

assignment_si <- (astro_assignment_plot | hep_assignment_plot) +
  plot_layout(axes = "collect_y") +
  plot_annotation(
    title = "Classification assignment sensitivities",
    subtitle = NULL,
    theme = theme(
      plot.title = element_text(
        family = REPORT_FONT,
        size = 10,
        hjust = 0.5,
        vjust = -0.9
      ),
      plot.subtitle = element_text(
        family = REPORT_FONT,
        size = 9,
        hjust = 0
      )
    )
  )


#"#FDE0C5FF", "#FACBA6FF", "#F8B58BFF", "#F59E72FF", "#F2855DFF", "#EF6A4CFF", "#EB4A40FF"



cross_plot <- crosslisting |>
  filter(year >= 2010, year <= 2025) |>
  ggplot(aes(year, crosslisting_rate)) +
  geom_ribbon(aes(ymin = crosslisting_low, ymax = crosslisting_high), fill = "#FACBA6FF", alpha = 0.5) +
  geom_line(color = "#EF6A4CFF") +
  geom_point(size = 1.1, color = "#EB4A40FF") +
  scale_x_continuous(breaks = c(2010, 2015, 2020, 2025)) +
  scale_y_continuous(
    limits = c(0.10, 0.25),
    labels = label_percent(accuracy = 1),
    expand = expansion(mult = c(0.02, 0.02))
      ) +
  labs(
    title = "Cross-field publication overlap",
    caption = "Between 16% and 20% of classified papers are linked to both fields each year", 
    x = NULL, 
    y = NULL
    ) +
  theme_report() +
  theme(
    plot.title = element_text(
      family = REPORT_FONT,
      size = 10,
      hjust = 0
    ),
    plot.subtitle = element_text(
      family = REPORT_FONT,
      size = 9,
      hjust = 0.0
    )
  )

assignment_block <- patchwork::wrap_elements(
  full = assignment_si,
  clip = FALSE
)
  

classification_si <- (volume_plot | cross_plot) / assignment_block +
  plot_layout(heights = c(0.7, 1.0)) +
  plot_annotation(tag_levels = "A") &
  theme(
    plot.tag = element_text(
      family = REPORT_FONT,
      size = 7
    ),
    plot.margin = margin(1, 5, 0, 5)
  )

if (interactive()) print(classification_si)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(classification_si, "figS1_classification_sensitivity.pdf", 220, 125)
}

# Step 3: Figure S2 -- raw candidate-family counts ----------------------------

raw_candidate_counts <- candidates |>
  filter(
    year >= 1995,
    year <= 2025,
    arxiv_category %in% names(FIELD_LABELS),
    SpeciesLabel %in% tracked_species
  ) |>
  distinct(year, arxiv_category, bibcode, SpeciesLabel) |>
  count(year, arxiv_category, SpeciesLabel, name = "n") |>
  mutate(
    field = recode(arxiv_category, !!!FIELD_LABELS),
    SpeciesLabel = factor(SpeciesLabel, levels = tracked_species)
  )

candidate_colors <- setNames(
  khroma::color("batlow", type = "qualitative", reverse = TRUE)(length(tracked_species)),
  tracked_species
)

raw_candidate_plot <- ggplot(
  raw_candidate_counts,
  aes(year, n, fill = SpeciesLabel)
) +
  geom_area(color = "white", linewidth = 0.08) +
  facet_wrap(~ field, nrow = 1, scales = "free_y") +
  scale_fill_manual(values = candidate_colors, drop = FALSE) +
  scale_x_continuous(breaks = seq(1995, 2025, 5)) +
  labs(
    title = "Raw paper-candidate-family mentions",
    x = NULL,
    y = "Paper-candidate-family mentions",
    fill = "Candidate"
  ) +
  theme_report(7.5) +
  theme(
    legend.position = "right",
    legend.text = element_text(size = 5.6),
    legend.key.height = grid::unit(2.6, "mm"),
    legend.key.width = grid::unit(2.2, "mm")
  )

if (interactive()) print(raw_candidate_plot)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(raw_candidate_plot, "figS2_candidate_raw_counts.pdf", 200, 85)
}

# Step 4: Figure S3 -- divergence, distances, and annual support --------------

js_plot <- candidate_divergence |>
  ggplot(aes(year, js_divergence)) +
  annotate("rect", xmin = 1994.5, xmax = 2004.5, ymin = -Inf, ymax = Inf, fill = "#EEEEEE", alpha = 0.4) +
  annotate("rect", xmin = 2015.5, xmax = 2025.5, ymin = -Inf, ymax = Inf, fill = "#EEEEEE", alpha = 0.4) +
  geom_ribbon(aes(ymin = js_low, ymax = js_high), fill = "#BFD3E6", alpha = 0.8) +
  geom_line(color = "#2F5F7F") +
  geom_point(color = "#2F5F7F") +
  scale_x_continuous(breaks = seq(1995, 2025, 5)) +
  scale_y_continuous(limits = c(0, NA)) +
  labs(
    title = "Jensen-Shannon divergence",
    caption = "Ribbon: 95% interval from 2,000 paper-level resamples per field-year",
    x = NULL,
    y = "Divergence"
  ) +
  theme_report(7.5)

distance_long <- candidate_divergence |>
  select(year, total_variation, cosine_distance) |>
  pivot_longer(-year, names_to = "metric", values_to = "distance") |>
  mutate(
    metric = recode(
      metric,
      total_variation = "Total variation",
      cosine_distance = "Cosine distance"
    )
  )

distance_plot <- distance_long |>
  ggplot(aes(year, distance, color = metric)) +
  geom_line(linewidth = 0.65) +
  scale_color_manual(
    values = c(
      "Total variation" = "#4DB6ACFF",
      "Cosine distance" = "goldenrod"
    )
  ) +
  scale_x_continuous(breaks = seq(1995, 2025, 5)) +
  scale_y_continuous(limits = c(0, NA)) +
  labs(
    title = "Alternative distance measures",
    x = NULL,
    y = NULL,
    color = NULL
  ) +
  theme_report(7.5) +
  theme(
    legend.position = "inside",
    legend.position.inside = c(0.98, 0.98),
    legend.justification = c(1, 1),
    legend.direction = "vertical",
    legend.background = element_rect(
      fill = scales::alpha("white", 0.8),
      color = NA
    ),
    legend.margin = margin(2, 2, 2, 2)
  )

annual_support <- candidate_divergence |>
  select(year, n_astro_papers, n_hep_papers) |>
  pivot_longer(-year, names_to = "field", values_to = "n_papers") |>
  mutate(
    field = recode(
      field,
      n_astro_papers = "Astrophysics",
      n_hep_papers = "High-energy physics"
    ),
    field_key = recode(
      field,
      "Astrophysics" = ASTRO,
      "High-energy physics" = HEP
    )
  )

sample_plot <- annual_support |>
  ggplot(aes(year, n_papers, color = field_key)) +
  geom_line(linewidth = 0.7) +
  scale_color_manual(values = FIELD_COLORS, labels = FIELD_LABELS) +
  scale_x_continuous(breaks = seq(1995, 2025, 5)) +
  scale_y_log10(labels = label_number(big.mark = ",")) +
  labs(
    title = "Candidate-mentioning papers supporting each annual estimate",
    caption = "Early field-years are based on substantially smaller samples.",
    x = NULL,
    y = "Papers (log scale)",
    color = NULL
  ) +
  theme_report(7.5) +
  theme(
    legend.position = "inside",
    legend.position.inside = c(0.2, 0.98),
    legend.justification = c(1, 1),
    legend.direction = "vertical",
    legend.background = element_rect(
      fill = scales::alpha("white", 0.8),
      color = NA
    ),
    legend.margin = margin(2, 2, 2, 2))

distance_figure <- (js_plot | distance_plot) / sample_plot +
  plot_layout(
    heights = c(1, 1),
    widths = c(1, 0.7)
  ) +
  plot_annotation(tag_levels = "A") &
  theme(
    plot.tag.position = c(-0.05, 1.2),
    plot.tag.location = "panel",
    plot.tag = element_text(
      family = REPORT_FONT,
      face = "bold",
      size = 8,
      hjust = 0,
      vjust = 1,
      margin = margin(10, 0, 5, 0)
    )
  )

if (interactive()) print(distance_figure)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(distance_figure, "figS3_candidate_distances.pdf", 180, 110)
}

# Step 5: Figure S4 -- lexical robustness and selected trajectories -----------

lexical_line <- lexical_divergence |>
  ggplot(aes(year, js_divergence, linetype = vocabulary_scope)) +
  geom_line(color = "cadetblue") +
  scale_x_continuous(
    breaks = seq(1995, 2025, 5),
    expand = expansion(mult = c(0.02, 0.02))
  ) +
  scale_linetype_manual(
    values = c("all unigrams" = "solid", "candidate terms removed" = "22"),
    labels = c(
      "all unigrams" = "All unigrams",
      "candidate terms removed" = "Predefined candidate-name unigrams removed"),
      guide = guide_legend(
        position = "inside",
        ncol = 1,
        byrow = TRUE,
        keywidth = grid::unit(10, "pt"),
        keyheight = grid::unit(8, "pt"),
        label.position = "left",
        label.hjust = 1
    )) +
  labs(
    title = "Vocabulary divergence persists after predefined candidate-name exclusions",
    x = NULL,
    y = "Jensen-Shannon divergence",
    linetype = NULL
  ) +
  theme_report() +
  theme(
    panel.grid.minor= element_blank(),
    legend.position.inside = c(0.8, 0.97),
    legend.background = element_rect(fill = alpha("white", 1), color = NA)
        )

excluded_trajectory_terms <- c(
  "tan", "host", "institute", "aims", "release", "datasets", "state-of-the-art",
  "potentially", "heavier", "constrain", "probed", "target", "benchmark",
  "simplified", "web", "fully", "additionally", "despite", "interestingly", "notably",
  "earlier", "thanks", "publicly", "competitive", "well-motivated", "challenging", "unexplored", "classical",
  "next-generation", "capable", "featuring", "designed", "real", "odd", "open", "rich", "deep", "projected",
  "achieved", "competitive", "revisit", "highlight", "induces", "trained", "satisfy",
  "integrated", "opens", "serves", "collected", "showing",
  "outline", "enable", "expectation", "findings", "program", "degrees", "science", "strategy",
  "article", "sets", "baseline", "band", "pairs", "utilizing", "employed", "offering", "modeling",
  "projections", "characteristics", "complexity", "questions", "impacts", "code",
  "digital", "statistical", "stacked", "unconstrained", "null", "https", "align", "cancellation", "forecast",
  "systems", "test", "sources", "times", "history", "fit",
  "state", "dependence", "spatial", "components", "functions", "mean", "average", "point", "estimates",
  "propose", "predict", "shows", "include", "conclude",
  "simulated", "dominated", "initial", "likely", "sensitive", "better", "additional",
  "local", "different", "possible", "available", "extended", "relative",
  "physical", "associated", "linear", "properties", "approach", "value", "values", "set",
  "total", "information", "size", "shape", "possibility",
  "investigate", "consider", "compared", "compare", "derived",
  "suggest", "proposed", "obtain", "explain", "measure", "given",
  "does", "produced", "future", "near", "mergers", "required", "accurate",
  "kpc", "pc", "mpc", "ev", "kev", "mev", "gev",
  "tev", "hz", "khz", "ghz", "mhz", "km", "yr", "yrs"
)

fit_endpoints <- function(yr, r) {
  if (sum(r > 0) < 4) return(c(NA_real_, NA_real_))
  fit <- stats::loess(
    r ~ yr,
    span = 0.75,
    degree = 1,
    control = stats::loess.control(surface = "direct")
  )
  stats::predict(fit, newdata = data.frame(yr = c(1995, 2025)))
}

unigram_trends <- unigrams |>
  filter(!term %in% excluded_trajectory_terms, year >= 1995) |>
  group_by(field, term) |>
  summarise(
    n_total = sum(n_kw),
    ends = list(fit_endpoints(year, rate)),
    .groups = "drop"
  ) |>
  mutate(
    early = purrr::map_dbl(ends, 1),
    late = purrr::map_dbl(ends, 2)
  ) |>
  filter(n_total >= 40, pmax(early, late, na.rm = TRUE) >= 0.005) |>
  mutate(log_growth = log2((pmax(late, 0) + 1e-4) / (pmax(early, 0) + 1e-4)))

selected_trajectories <- unigram_trends |>
  mutate(direction = if_else(log_growth > 0, "rising", "declining")) |>
  group_by(field, direction) |>
  filter(abs(log_growth) >= 0.3) |>
  slice_max(abs(log_growth), n = 5, with_ties = FALSE) |>
  ungroup() |>
  arrange(field, direction, desc(abs(log_growth)))

trajectory_data <- unigrams |>
  semi_join(selected_trajectories, by = c("field", "term")) |>
  left_join(
    selected_trajectories |> select(field, term, direction, log_growth),
    by = c("field", "term")
  ) |>
  filter(n_papers >= 40)

rising_astro <- trajectory_data |>
  filter(direction == "rising", field == "Astrophysics") |>
  distinct(term) |>
  pull() |>
  sort()
declining_astro <- trajectory_data |>
  filter(direction == "declining", field == "Astrophysics") |>
  distinct(term) |>
  pull() |>
  sort()
rising_hep <- trajectory_data |>
  filter(direction == "rising", field == "High-energy physics") |>
  distinct(term) |>
  pull() |>
  sort()
declining_hep <- trajectory_data |>
  filter(direction == "declining", field == "High-energy physics") |>
  distinct(term) |>
  pull() |>
  sort()

astro_trajectory_colors <- c(
  setNames(viridisLite::viridis(length(rising_astro), option = "D", begin = 0.0, end = 0.95), rising_astro),
  setNames(viridisLite::viridis(length(declining_astro), option = "B", begin = 0.0, end = 0.9), declining_astro)
)
hep_trajectory_colors <- c(
  setNames(viridisLite::viridis(length(rising_hep), option = "D", begin = 0.0, end = 0.95), rising_hep),
  setNames(viridisLite::viridis(length(declining_hep), option = "B", begin = 0.0, end = 0.9), declining_hep)
)

astro_header <- patchwork::wrap_elements(grid::gTree(children = grid::gList(
  grid::textGrob(
    "Astrophysics",
    x = 0.01,
    hjust = 0,
    gp = grid::gpar(fontsize = 7, fontfamily = REPORT_FONT)
  )
)))
hep_header <- patchwork::wrap_elements(grid::textGrob(
  "High-energy physics",
  x = 0.01,
  hjust = 0,
  gp = grid::gpar(fontsize = 7, fontfamily = REPORT_FONT)
))

make_lexical_panel <- function(
  data,
  field_name,
  direction_name,
  colors,
  upper_limit,
  y_label,
  legend_x,
  top_margin = 0
) {
  decreasing <- identical(direction_name, "declining")
  data |>
    filter(direction == direction_name, field == field_name) |>
    ggplot(aes(x = year, y = rate, color = term, group = term)) +
    geom_line(alpha = 0.85) +
    scale_color_manual(
      values = colors,
      name = if (decreasing) "Decreasing" else "Increasing",
      labels = scales::label_wrap(if (decreasing) 25 else 30),
      guide = guide_legend(
        position = "inside",
        ncol = 1,
        byrow = TRUE,
        keywidth = grid::unit(8, "pt"),
        keyheight = grid::unit(6, "pt"),
        label.position = if (decreasing) "left" else "right",
        label.hjust = if (decreasing) 1 else 0
      )
    ) +
    scale_x_continuous(
      breaks = seq(1995, 2025, by = 5),
      expand = expansion(mult = c(0.02, 0.02))
    ) +
    scale_y_continuous(trans = "sqrt", labels = scales::percent_format(accuracy = 1)) +
    coord_cartesian(ylim = c(0, upper_limit)) +
    labs(title = NULL, x = NULL, y = y_label) +
    theme_report() +
    theme(
      legend.position = c(legend_x, 0.78),
      panel.grid.minor = element_blank(),
      plot.margin = margin(top_margin, 5, 5, 5),
      legend.background = element_rect(
        fill = scales::alpha("white", 1.0),
        color = NA
      ),
      legend.text = element_text(size = 6, margin = margin(r = 0.2, unit = "pt")),
      legend.title = element_text(
        size = 7,
        family = REPORT_FONT,
        color = "black",
        hjust = if (decreasing) 1 else 0
      ),
      panel.grid.major.x = element_blank()
    )
}

astro_declining_plot <- make_lexical_panel(
  trajectory_data,
  "Astrophysics",
  "declining",
  astro_trajectory_colors,
  0.15,
  "Fraction of papers (%)",
  0.92
)
astro_rising_plot <- make_lexical_panel(
  trajectory_data,
  "Astrophysics",
  "rising",
  astro_trajectory_colors,
  0.15,
  NULL,
  0.09
)
hep_declining_plot <- make_lexical_panel(
  trajectory_data,
  "High-energy physics",
  "declining",
  hep_trajectory_colors,
  0.45,
  "Fraction of papers (%)",
  0.92,
  -10
)
hep_rising_plot <- make_lexical_panel(
  trajectory_data,
  "High-energy physics",
  "rising",
  hep_trajectory_colors,
  0.45,
  NULL,
  0.17
)

lexical_design <- "
  AA
  BC
  DD
  EF
"
trajectory_figure <- astro_header + astro_declining_plot + astro_rising_plot +
  hep_header + hep_declining_plot + hep_rising_plot +
  patchwork::plot_layout(
    design = lexical_design,
    heights = c(0.85, 10, 0.85, 10),
    axes = "collect"
  ) +
  theme(plot.margin = margin(-55, 5, -25, 5))

lexical_figure <- lexical_line / patchwork::wrap_elements(full = trajectory_figure) +
  plot_layout(heights = c(0.55, 1.40)) &
  plot_annotation(tag_levels = "A") &
theme(
    plot.tag = element_text(
      family = REPORT_FONT,
      face = "bold",
      size = 8,
      hjust = 0,
      vjust = 0,
      margin = margin(-4, 0, 0, 0)
    )
  )  

if (interactive()) print(lexical_figure)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(lexical_figure, "figS4_lexical_divergence.pdf", 200, 145)
}

message("SI figures finished.")
if (SAVE_OUTPUTS) {
  message("  ", file.path(FIGURE_OUTPUT_DIR, "figS1_classification_sensitivity.pdf"))
  message("  ", file.path(FIGURE_OUTPUT_DIR, "figS2_candidate_raw_counts.pdf"))
  message("  ", file.path(FIGURE_OUTPUT_DIR, "figS3_candidate_distances.pdf"))
  message("  ", file.path(FIGURE_OUTPUT_DIR, "figS4_lexical_divergence.pdf"))
} else {
  message("  SAVE_OUTPUTS is FALSE; plot objects remain in memory and no PDFs were written.")
}
