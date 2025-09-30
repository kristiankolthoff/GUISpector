# --- Packages ---
suppressPackageStartupMessages(library(irr))

csv_path <- ""

dat <- read.csv2(csv_path, stringsAsFactors = FALSE, check.names = FALSE)

needed_cols <- c("AI", "ANN1 - Post")
cols <- needed_cols

clean_str <- function(x) {
  x <- trimws(tolower(x))
  x <- gsub("[ ]+", "", x)
  x
}
dat[cols] <- lapply(dat[cols], clean_str)

valid_levels <- c("not_met", "partially_met", "met")

found   <- sort(unique(unlist(dat[cols])))
unknown <- setdiff(found, c(valid_levels, NA, ""))
if (length(unknown) > 0) {
  warning("Unknown labels found: ",
          paste(unknown, collapse = ", "),
          "\nExpected: not_met, partially_met, met")
}

for (nm in cols) {
  x <- dat[[nm]]
  x[x == ""] <- NA
  dat[[nm]] <- factor(x, levels = valid_levels, ordered = FALSE)
}

ratings_df <- dat[cols]

kappa_nominal <- irr::kappa2(ratings_df, weight = "unweighted")
cat("\nCohen's Kappa (nominal):\n")
print(kappa_nominal)

kappa_weighted_linear <- irr::kappa2(ratings_df, weight = "equal")
cat("\nCohen's Kappa (ordinal, linear weights):\n")
print(kappa_weighted_linear)

kappa_weighted_quad <- irr::kappa2(ratings_df, weight = "squared")
cat("\nCohen's Kappa (ordinal, quadratic weights):\n")
print(kappa_weighted_quad)

cat("\nConfusion Matrix (AI vs. ANN1 - Post):\n")
print(table(AI = dat$AI, Gold = dat[["ANN1 - Post"]]))