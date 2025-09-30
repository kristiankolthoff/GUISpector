# --- Packages ---
suppressPackageStartupMessages({
  library(irr)
  library(dplyr)
})

csv_path <- ""

# read.csv2() defaults: sep=";", dec=","
dat <- read.csv2(csv_path, stringsAsFactors = FALSE, check.names = FALSE)

needed_cols <- c("APPs/RQs", "ANN1 - Ante", "ANN2 - Ante")

col_map  <- setNames(names(dat), tolower(names(dat)))
need_map <- tolower(needed_cols)
if (!all(need_map %in% names(col_map))) {
  stop("Required columns not found.\nAvailable: ",
       paste(names(dat), collapse = ", "),
       "\nExpected: ", paste(needed_cols, collapse = ", "))
}
cols <- unname(col_map[need_map])

clean_str <- function(x) {
  x <- trimws(tolower(x))
  x <- gsub("[ ]+", "", x)
  x
}
dat[cols[2:3]] <- lapply(dat[cols[2:3]], clean_str)

valid_levels <- c("not_met", "met")

# Check for unexpected labels
found   <- sort(unique(unlist(dat[cols[2:3]])))
unknown <- setdiff(found, c(valid_levels, NA, ""))
if (length(unknown) > 0) {
  warning("Unknown labels found: ",
          paste(unknown, collapse = ", "),
          "\nExpected exactly: not_met, met")
}

for (nm in cols[2:3]) {
  x <- dat[[nm]]
  x[x == ""] <- NA
  dat[[nm]] <- factor(x, levels = valid_levels, ordered = FALSE)
}

ratings_df <- dat[cols[2:3]]
kappa_nominal <- irr::kappa2(ratings_df, weight = "unweighted")

cat("\nPooled Cohen's Kappa (ANN1-Ante vs ANN2-Ante, nominal):\n")
print(kappa_nominal)

# Accuracy and confusion matrix (helpful context)
cat("\nConfusion Matrix (ANN1-Ante vs ANN2-Ante):\n")
print(table(ANN1 = dat[[cols[2]]], ANN2 = dat[[cols[3]]]))

acc <- mean(dat[[cols[2]]] == dat[[cols[3]]], na.rm = TRUE)
cat(sprintf("\nPooled accuracy: %.1f%% (%d/%d)\n",
            100*acc, sum(dat[[cols[2]]] == dat[[cols[3]]], na.rm = TRUE),
            sum(complete.cases(dat[cols[2:3]]))))

dat$App <- sub("\\s*-.*$", "", dat[[cols[1]]])

per_app <- dat %>%
  group_by(App) %>%
  summarise(
    items = sum(complete.cases(.data[[cols[2]]], .data[[cols[3]]])),  # count usable items
    kappa = {
      sub_df <- data.frame(
        a1 = .data[[cols[2]]],
        a2 = .data[[cols[3]]]
      )
      sub_df <- sub_df[complete.cases(sub_df), , drop = FALSE]
      if (nrow(sub_df) > 0) irr::kappa2(sub_df, weight = "unweighted")$value else NA_real_
    },
    .groups = "drop"
  ) %>%
  arrange(App)

cat("\nPer-app Cohen's Kappa (nominal):\n")
print(per_app, n = Inf)

set.seed(123)
B <- 2000
n <- nrow(ratings_df)
idx_complete <- complete.cases(ratings_df)
ratings_complete <- ratings_df[idx_complete, , drop = FALSE]
n_complete <- nrow(ratings_complete)

boot_vals <- replicate(B, {
  idx <- sample.int(n_complete, n_complete, replace = TRUE)
  irr::kappa2(ratings_complete[idx, , drop = FALSE], weight = "unweighted")$value
})

ci <- quantile(boot_vals, c(0.025, 0.975), na.rm = TRUE)
cat("\nBootstrap 95% CI for pooled Cohen's Kappa (nominal):\n")
print(ci)