# Project Overview

This folder contains three parts:

- **Annotations** – App specifications with annotations (before/after agreements).  
- **Application-Requirement-Generation** – Generated app HTML files (used in evaluations) and requirement specifications without annotations, plus prompt templates.  
- **Evaluations** – R scripts to calculate Cohen’s kappa and Krippendorff’s alpha for agreement analysis.

## Structure

```
├── Annotations
│   ├── 01_park-and-pay.json
│   ├── 02_budget-tracker.json
│   ├── 03_recipe-generator.json
│   ├── 04_fitness-challenges.json
│   └── 05_cleaning-booking.json
│
├── Application-Requirement-Generation
│   ├── 00_Prompts_App_Generation.txt
│   ├── 00_Prompts_Requirement_Generation.txt
│   ├── XX_app.html
│   └── XX_app_requirements.json
│
└── Evaluations
    ├── Cohen_ACs_ANN1_ANN2.R
    ├── Cohen_REQ_AI_ANN1_ANN2.R
    └── Krippendorff_REQ_AI_ANN1_ANN2.R
```
