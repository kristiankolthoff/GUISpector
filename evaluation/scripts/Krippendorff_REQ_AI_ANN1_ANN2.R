# --- Packages ---
suppressPackageStartupMessages(library(irr))

csv_path <- ""

dat <- read.csv2(csv_path, stringsAsFactors = FALSE, check.names = FALSE)

needed_cols <- c("AI", "ANN1 - Ante", "ANN2 - Ante")

col_map  <- setNames(names(dat), tolower(names(dat)))
need_map <- tolower(needed_cols)
if (!all(need_map %in% names(col_map))) {
  stop(
    "Not all required columns were found.\nAvailable: ",
    paste(names(dat), collapse = ", "),
    "\nExpected: ", paste(needed_cols, collapse = ", ")
  )
}
cols <- col_map[need_map]

clean_str <- function(x) {
  x <- trimws(tolower(x))
  x <- gsub("[ ]+", "", x)
  x
}
dat[cols] <- lapply(dat[cols], clean_str)

valid_levels <- c("not_met","partially_met","met")

found   <- sort(unique(unlist(dat[cols])))
unknown <- setdiff(found, c(valid_levels, NA, ""))
if (length(unknown) > 0) {
  warning(
    "Unknown labels found: ",
    paste(unknown, collapse = ", "),
    "\nExpected exactly: not_met, partially_met, met."
  )
}

ord_map <- c("not_met"=1, "partially_met"=2, "met"=3)

# Empty strings => NA, then map
for (nm in cols) {
  v <- dat[[nm]]
  v[v == ""] <- NA
  dat[[nm]] <- unname(ord_map[v]) 
}

cat("NAs per rater:\n")
print(sapply(dat[cols], function(v) sum(is.na(v))))

ratings_num <- t(as.matrix(dat[cols]))  # numeric 1 < 2 < 3

alpha_nominal <- irr::kripp.alpha(ratings_num, method = "nominal")
alpha_ordinal <- irr::kripp.alpha(ratings_num, method = "ordinal")

cat("\nKrippendorff's Alpha (nominal):\n");  print(alpha_nominal)
cat("\nKrippendorff's Alpha (ordinal):\n");  print(alpha_ordinal)

set.seed(123)
B <- 2000
n_items <- ncol(ratings_num)

boot_vals <- replicate(B, {
  idx <- sample.int(n_items, n_items, replace = TRUE)
  suppressWarnings(
    tryCatch(
      irr::kripp.alpha(ratings_num[, idx, drop = FALSE], method = "ordinal")$value,
      error = function(e) NA_real_
    )
  )
})
mean(is.na(boot_vals)) 

ci <- quantile(boot_vals, c(0.025, 0.975), na.rm = TRUE)
cat("\nBootstrap 95% CI (ordinal):\n"); print(ci)

summary_df <- data.frame(
  measure = c("alpha_nominal", "alpha_ordinal", "alpha_ordinal_CI_low", "alpha_ordinal_CI_high"),
  value   = c(alpha_nominal$value, alpha_ordinal$value, ci[1], ci[2])
)
print(summary_df, row.names = FALSE)
