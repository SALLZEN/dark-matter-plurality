#!/usr/bin/env Rscript

# Stepwise companion to 006-build-paper-assets.R
#
# Purpose:
#   Run the paper-asset workflow one section at a time in an IDE, inspect the
#   intermediate data objects, and see plots in the plot pane as they are built.
#
# Recommended use in RStudio:
#   1. Open this file.
#   2. Run each section in order.
#   3. Keep SAVE_OUTPUTS <- FALSE while exploring.
#   4. Switch SAVE_OUTPUTS <- TRUE only when you want to write the final assets.

detect_stepwise_dir <- function() {
  script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(script_arg)) {
    script_path <- sub("^--file=", "", script_arg[[1]])
    return(dirname(normalizePath(script_path, winslash = "/", mustWork = TRUE)))
  }
  if (!is.null(sys.frames()[[1]]$ofile)) {
    return(dirname(normalizePath(sys.frames()[[1]]$ofile, winslash = "/", mustWork = TRUE)))
  }
  root_launch_path <- file.path(getwd(), "code", "006a-build-paper-assets-stepwise.R")
  if (file.exists(root_launch_path)) {
    return(dirname(normalizePath(root_launch_path, winslash = "/", mustWork = TRUE)))
  }
  normalizePath(getwd(), winslash = "/", mustWork = TRUE)
}

STEPWISE_DIR <- detect_stepwise_dir()

# Main manuscript figures ------------------------------------------------------
#
# This section is the supported, stepwise route for Figures 1--3. It reads the
# frozen analysis products directly, keeps each intermediate object visible in
# an IDE, and writes the exact filenames used by the manuscript. Set
# PNAS_WORKSPACE_ROOT when this companion is run outside this repository's code/ directory;
# set PNAS_FIGURE_OUTPUT_DIR to redirect the generated PDFs.

suppressWarnings(suppressPackageStartupMessages({
  library(arrow)
  library(dplyr)
  library(ggplot2)
  library(khroma)
  library(patchwork)
  library(scales)
  library(stringr)
  library(tidyr)
}))

SAVE_OUTPUTS <- TRUE
BASE_FONT <- "STIX Two Text"
REPORT_FONT <- BASE_FONT

workspace_candidates <- c(
  Sys.getenv("PNAS_WORKSPACE_ROOT", unset = ""),
  normalizePath(file.path(STEPWISE_DIR, ".."), winslash = "/", mustWork = FALSE)
)
workspace_candidates <- unique(workspace_candidates[nzchar(workspace_candidates)])
workspace_has_inputs <- vapply(
  workspace_candidates,
  function(path) {
    file.exists(file.path(path, "data", "analysis", "classification_primary_yearly.parquet")) &&
      file.exists(file.path(path, "data", "analysis", "candidate_field_yearly.parquet")) &&
      file.exists(file.path(path, "data", "dm_model_candidates_long.parquet"))
  },
  logical(1)
)

if (!any(workspace_has_inputs)) {
  stop(
    paste(
      "Could not locate the frozen workspace data.",
      "Set PNAS_WORKSPACE_ROOT to the directory containing data/analysis."
    ),
    call. = FALSE
  )
}

WORKSPACE_ROOT <- normalizePath(workspace_candidates[workspace_has_inputs][[1]], winslash = "/", mustWork = TRUE)
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
if (all(nzchar(font_matches$path)) && all(file.exists(font_matches$path))) {
  sysfonts::font_add(
    family = REPORT_FONT,
    regular = font_matches$path[[1]],
    bold = font_matches$path[[1]],
    italic = font_matches$path[[2]],
    bolditalic = font_matches$path[[2]]
  )
  showtext::showtext_auto()
}

theme_nature <- function(base_size = 7) {
  theme_light(base_size = base_size, base_family = BASE_FONT) +
    theme(
      panel.grid = element_blank(),
      panel.background = element_rect(fill = "white", color = NA),
      plot.background = element_rect(fill = "white", color = NA),
      text = element_text(family = BASE_FONT, color = "black", size = base_size),
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

# Step 1: load and inspect the frozen inputs ----------------------------------

primary <- read_parquet(file.path(ANALYSIS_DIR, "classification_primary_yearly.parquet"))
assignments <- read_parquet(file.path(ANALYSIS_DIR, "classification_assignment_yearly.parquet"))
candidate_field <- read_parquet(file.path(ANALYSIS_DIR, "candidate_field_yearly.parquet"))
candidates <- read_parquet(file.path(DATA_DIR, "dm_model_candidates_long.parquet"))
tracked_species <- readLines(file.path(ANALYSIS_DIR, "tracked_candidate_species.txt"))
unigrams <- read_parquet(file.path(DATA_DIR, "unigram_yearly.parquet"))

message("Loaded frozen analysis products from: ", WORKSPACE_ROOT)
message("  classification_primary_yearly: ", nrow(primary), " rows")
message("  classification_assignment_yearly: ", nrow(assignments), " rows")
message("  candidate_field_yearly: ", nrow(candidate_field), " rows")
message("  dm_model_candidates_long: ", nrow(candidates), " rows")

# Step 2: Figure 1 -- composition_plot_wide_guide -----------------------------

FIELD_LABELS <- c(
  "astrophysics" = "Astrophysics",
  "high-energy physics" = "High-energy physics"
)
FIELD_COLORS <- c(
  "astrophysics" = "#f98689",
  "high-energy physics" = "#abdad9"
)

shared_categories <- primary |>
  filter(year >= 2010, year <= 2025) |>
  group_by(arxiv_class) |>
  summarise(total = sum(n_papers), .groups = "drop") |>
  slice_max(total, n = 7, with_ties = FALSE) |>
  pull(arxiv_class)

pal <- scales::gradient_n_pal(khroma::color("batlow", reverse = TRUE)(256))
shared_cols <- pal(seq(0, 1, length.out = length(shared_categories)))
shared_col_map <- setNames(shared_cols, shared_categories)

class_data <- primary |>
  filter(year >= 2010, year <= 2025, arxiv_class %in% shared_categories)

class_winner <- class_data |>
  group_by(year) |>
  mutate(prop = n_papers / sum(n_papers)) |>
  slice_max(n_papers, n = 1, with_ties = FALSE) |>
  ungroup() |>
  mutate(text_col = if_else(arxiv_class == "hep-ex", "white", "black"))

paper_plot_wide <- class_data |>
  ggplot(aes(x = year, y = n_papers, color = arxiv_class, group = arxiv_class)) +
  geom_line(linewidth = 0.65, alpha = 0.9) +
  scale_color_manual(values = shared_col_map, breaks = shared_categories, drop = FALSE) +
  scale_x_continuous(
    breaks = seq(2010, 2025, by = 5),
    expand = expansion(mult = c(0.02, 0.02))
  ) +
  scale_y_continuous(
    trans = "sqrt",
    breaks = c(50, 100, 500, 1000, 2000, 3000),
    labels = scales::label_number(scale_cut = scales::cut_short_scale()),
    expand = expansion(mult = c(0.02, 0.00))
  ) +
  labs(x = NULL, y = "Papers/year (sqrt)", color = NULL) +
  theme_minimal(base_size = 10, base_family = REPORT_FONT) +
  guides(color = guide_legend(
    nrow = 1,
    byrow = TRUE,
    title = NULL,
    label.position = "right",
    override.aes = list(linewidth = 2.2, alpha = 1),
    keywidth = grid::unit(6, "pt"),
    keyheight = grid::unit(5, "pt")
  )) +
  theme(
    legend.position = "top",
    legend.frame = element_rect(fill = NA, color = "gray55"),
    legend.text = element_text(size = 7.5),
    axis.title.y = element_text(size = 8),
    axis.text.x = element_text(size = 8),
    axis.ticks.x = element_blank(),
    axis.title.x = element_blank(),
    plot.margin = margin(0, 5, 1, 5)
  )

papers_strip <- ggplot(class_winner, aes(x = year, y = "Top share", fill = arxiv_class)) +
  geom_tile(color = "white", linewidth = 0.5) +
  geom_text(
    aes(
      label = scales::percent(prop, accuracy = 0.1),
      color = text_col
    ),
    size = 2.5,
    lineheight = 0.5
  ) +
  scale_x_continuous(
    breaks = seq(2010, 2025, by = 1),
    expand = expansion(mult = c(-0.02, -0.02))
  ) +
  scale_y_discrete(
    breaks = NULL,
    expand = expansion(mult = c(0.0, 0.0))
  ) +
  coord_cartesian(clip = "off") +
  scale_fill_manual(values = shared_col_map) +
  scale_color_identity() +
  labs(x = NULL, y = NULL, fill = NULL) +
  theme_minimal(base_size = 10, base_family = REPORT_FONT) +
  theme(
    panel.grid = element_blank(),
    panel.border = element_blank(),
    axis.title.y = element_text(angle = 0, hjust = 0.5, vjust = 0.5),
    axis.text.y = element_blank(),
    axis.ticks.y = element_blank(),
    legend.position = "none"
  )

broad_primary <- assignments |>
  filter(
    year >= 2010,
    year <= 2025,
    assignment == "primary",
    arxiv_category %in% names(FIELD_LABELS)
  ) |>
  mutate(field = recode(arxiv_category, !!!FIELD_LABELS))

broad_plot <- broad_primary |>
  ggplot(aes(year, share, color = arxiv_category)) +
  geom_line(linewidth = 0.8) +
  scale_color_manual(values = FIELD_COLORS, labels = FIELD_LABELS) +
  scale_x_continuous(
    breaks = c(2010, 2015, 2020, 2025),
    expand = expansion(mult = c(0, 0)),
    limits = c(2010, 2025)
  ) +
  scale_y_continuous(
    labels = label_percent(accuracy = 1),
    limits = c(0.2, 0.6),
    expand = expansion(mult = c(0.02, 0.05))
  ) +
  labs(x = NULL, y = NULL, color = NULL) +
  theme_minimal(base_family = REPORT_FONT, base_size = 10) +
  guides(color = guide_legend(
    nrow = 1,
    override.aes = list(linewidth = 2.2, alpha = 1),
    keywidth = grid::unit(6, "pt")
  )) +
  theme(
    legend.position = "top",
    legend.frame = element_rect(fill = NA, color = "gray55"),
    legend.text = element_text(size = 7.5, family = REPORT_FONT),
    axis.text = element_text(size = 8),
    axis.ticks.x = element_blank(),
    axis.title = element_blank(),
    plot.margin = margin(0, 5, 1, 5)
  )

composition_plot_wide_guide <-
  broad_plot +
  paper_plot_wide +
  papers_strip +
  plot_layout(
    design = "
      AB
      AC
    ",
    widths = c(1, 1.25),
    heights = c(9.3, 0.7),
    guides = "keep",
    axes = "collect"
  ) &
  plot_annotation(
    title = "Field dominance by arXiv class and category"
  ) &
  theme(
    legend.box = "horizontal",
    legend.direction = "horizontal",
    legend.byrow = TRUE,
    legend.box.just = "left",
    plot.title = element_text(size = 11, family = REPORT_FONT, hjust = 0.5, vjust = 0.5),
    plot.tag = element_text(size = 7, family = REPORT_FONT),
    plot.tag.position = c(0.01, 0.98),
    axis.text = element_text(size = 7),
    axis.title.x = element_blank(),
    plot.margin = margin(5, 5, 1, 5)
  )

if (interactive()) print(composition_plot_wide_guide)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(composition_plot_wide_guide, "primary_dominant.pdf", 220, 100)
}

# Step 3: Figure 2 -- log_ratio_plot ------------------------------------------

MIN_TOTAL_MENTIONS <- 20L

candidate_field_plot <- candidate_field |>
  mutate(SpeciesLabel = stringr::str_replace(SpeciesLabel, fixed("Sterile nu"), "Sterile ν"))

stopifnot(all(
  candidate_field_plot$meets_minimum_count ==
    (candidate_field_plot$total_mentions >= MIN_TOTAL_MENTIONS)
))

species_order <- candidate_field_plot |>
  filter(year >= 1995, year <= 2025, total_mentions >= MIN_TOTAL_MENTIONS) |>
  group_by(SpeciesLabel) |>
  summarise(
    mean_ratio = weighted.mean(log2_hep_astro_ratio, w = total_mentions, na.rm = TRUE),
    .groups = "drop"
  ) |>
  arrange(mean_ratio) |>
  pull(SpeciesLabel)

log_ratio_data <- candidate_field_plot |>
  filter(year >= 1995, year <= 2025, SpeciesLabel %in% species_order) |>
  mutate(
    SpeciesLabel = factor(SpeciesLabel, levels = species_order),
    shown_ratio = if_else(total_mentions >= MIN_TOTAL_MENTIONS, log2_hep_astro_ratio, NA_real_)
  )

div <- c(
  "#00429d", "#2b57a7", "#426cb0", "#5681b9", "#6997c2",
  "#7daeca", "#93c4d2", "#abdad9", "#caefdf", "#ffffe0",
  "#ffe2ca", "#ffc4b4", "#ffa59e", "#f98689", "#ed6976",
  "#dd4c65", "#ca2f55", "#b11346", "#93003a"
)


log_ratio_plot <- log_ratio_data |>
  ggplot(aes(year, SpeciesLabel, fill = shown_ratio)) +
  geom_tile(color = "white", linewidth = 0.15, alpha = 0.85) +
  scale_x_continuous(
    breaks = seq(1995, 2025, 2),
    expand = expansion(mult = c(0.01, 0))
  ) +
  scale_fill_gradientn(
    colours = div,
    name = "Share ratio",
    limits = c(-log2(10), log2(10)),
    breaks = c(-log2(10), -log2(3), 0, log2(3), log2(10)),
    labels = c("10× Astro", "3× Astro", "1×", "3× HEP", "10× HEP"),
    oob = scales::squish,
    na.value = "white",
    guide = guide_colorbar(
      direction = "horizontal",
      title.position = "top",
      title.hjust = 0,
      title.vjust = 0.3,
      barwidth = grid::unit(70, "mm"),
      barheight = grid::unit(3.5, "mm"),
      ticks.colour = "white"
    )
  ) +
  labs(
    x = NULL,
    y = NULL,
    title = "Relative prominence of candidates",
    subtitle = "Log2 ratio of HEP to astrophysics shares, 1995-2025"
  ) +
  theme_minimal(base_family = REPORT_FONT, base_size = 8) +
  theme(
    plot.title = element_text(size = 11, family = REPORT_FONT, hjust = 0),
    plot.subtitle = element_text(size = 8, family = REPORT_FONT, hjust = 0),
    plot.margin = margin(10, 10, 5, 4),
    panel.grid.major = element_line(color = "black", linewidth = 0.1),
    panel.grid.minor = element_blank(),
    legend.title = element_text(size = 6, family = REPORT_FONT, color = "black"),
    legend.position = "bottom"
  )

if (interactive()) print(log_ratio_plot)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(log_ratio_plot, "log_ratio.pdf", 200, 88)
}

# Step 4: Figure 3 -- candidate_robustness -----------------------------------

tracked_species <- stringr::str_replace(tracked_species, fixed("Sterile nu"), "Sterile ν")
candidate_norm <- candidates |>
  mutate(SpeciesLabel = stringr::str_replace(SpeciesLabel, fixed("Sterile nu"), "Sterile ν")) |>
  filter(
    year >= 1995,
    year <= 2025,
    arxiv_category %in% names(FIELD_LABELS),
    SpeciesLabel %in% tracked_species
  ) |>
  distinct(year, arxiv_category, bibcode, SpeciesLabel) |>
  count(year, arxiv_category, SpeciesLabel, name = "n") |>
  group_by(year, arxiv_category) |>
  mutate(share_tracked_candidates = n / sum(n)) |>
  ungroup() |>
  mutate(
    field = recode(arxiv_category, !!!FIELD_LABELS),
    SpeciesLabel = factor(SpeciesLabel, levels = tracked_species)
  )

candidate_colors <- setNames(
  khroma::color("batlow", type = "qualitative", reverse = TRUE)(length(tracked_species)),
  tracked_species
)

p_norm <- candidate_norm |>
  ggplot(aes(year, share_tracked_candidates, fill = SpeciesLabel)) +
  geom_area(position = "fill", alpha = 0.89, linewidth = 0.15, color = "white") +
  facet_wrap(~ field, ncol = 2, scales = "fixed") +
  scale_fill_manual(values = candidate_colors, name = NULL, drop = FALSE) +
  scale_x_continuous(
    breaks = seq(1995, 2025, 5),
    expand = expansion(mult = c(0.01, 0))
  ) +
  scale_y_continuous(
    labels = scales::percent_format(accuracy = 1),
    expand = expansion(mult = c(0.01, 0))
  ) +
  labs(x = NULL, 
       title = "Share of paper-candidate-family mentions", 
       subtitle = "Normalized to total mentions in each field, 1995-2025",
       y = NULL) +
  theme_minimal(base_size = 10, base_family = REPORT_FONT) +
  theme(
    panel.spacing = grid::unit(1.5, "lines"),
    plot.margin = margin(0, 0, 0, 0),
    strip.background = element_rect(color = NA, fill = NA),
    strip.text = element_text(color = "#141414"),
    strip.text.x.bottom = element_text(hjust = 0.5, vjust = 0.5),
    axis.ticks.x = element_blank(),
    legend.position = "right",
    legend.key.spacing.y = grid::unit(0.2, "lines")
  ) +
  guides(fill = guide_legend(
    ncol = 1,
    byrow = TRUE,
    title.position = "bottom",
    title.hjust = 0.5,
    label.position = "right",
    override.aes = list(alpha = 1, size = 1.5, shape = 15),
    keywidth = grid::unit(10, "pt"),
    keyheight = grid::unit(5, "pt")
  ))

candidate_robustness <- p_norm +
  patchwork::plot_layout(widths = 1, axes = "collect", guides = "keep") &
  theme(
    plot.title = element_text(size = 11, color = "black", hjust = 0, vjust = 0.2),
    plot.subtitle = element_text(size = 8, color = "black", hjust = 0, vjust = 1),
    plot.margin = margin(1, 5, 5, 5),
    panel.margin  = grid::unit(0.5, "lines"),
    legend.margin = margin(0, 0, 0, 0),
    legend.position = "right",
    legend.box = "horizontal",
    legend.box.just = "left",
    panel.grid.major = element_line(color = "black", linewidth = 0.15),
    panel.grid.minor = element_blank(),
    legend.background = element_blank(),
    legend.key.spacing = grid::unit(3.4, "pt"),
    legend.text = element_text(size = 6.5, margin = margin(l = 1.5, r = 0.2, unit = "pt")),
    legend.title = element_text(size = 7, family = BASE_FONT, color = "black", hjust = 0)
  )

if (interactive()) print(candidate_robustness)
if (SAVE_OUTPUTS) {
  save_stepwise_pdf(candidate_robustness, "norm.pdf", 200, 95)
}

message("Main manuscript figures finished.")
message("  ", file.path(FIGURE_OUTPUT_DIR, "primary_dominant.pdf"))
message("  ", file.path(FIGURE_OUTPUT_DIR, "log_ratio.pdf"))
message("  ", file.path(FIGURE_OUTPUT_DIR, "norm.pdf"))
