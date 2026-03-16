# Custom Columns Guide

Your dashboard now has a full custom column system! Access it via the **Settings** tab.

## Features

### 1. Custom Data Columns
**Purpose:** Add metadata fields to store custom information about each project

**Examples:**
- Project Owner: "John Doe"
- Priority: "High"
- Status: "Active"
- Department: "Sales"

**How to use:**
1. Go to Settings tab
2. Click "Add New Data Column"
3. Enter column name (e.g., "Project Owner")
4. Select data type (Text/Number/Date)
5. Set default value (optional)
6. Click "Add Data Column"
7. Click "Edit" to set values for each project

### 2. Custom Calculated Columns
**Purpose:** Create formula-based columns using pandas eval syntax

**Examples:**
- Usage efficiency: `usage_last_30_days / (Investment + 1)`
- ROI per month: `cumulative_cost_saved / 12`
- Savings rate: `cost_saved_30d / (cost_saved_30d + Monthly_ROI_Goal)`

**How to use:**
1. Go to Settings tab
2. Click "Add New Calculated Column"
3. Enter column name (e.g., "Usage_per_1000")
4. Enter formula (e.g., `usage_last_30_days / (Investment / 1000)`)
5. Click "Add Calculated Column"

**Available fields for formulas:**
- `usage_last_30_days`, `usage_last_3_months`, `usage_last_12_months`
- `cost_saved_30d`, `cost_saved_3mo`, `cost_saved_12mo`
- `Investment`, `Monthly_ROI_Goal`, `Client_Hourly_Rate`
- `time_saved_hours_30d`, `time_saved_hours_3mo`, `time_saved_hours_12mo`
- `roi_progress_percent`, `mom_usage_percent`
- Any custom data columns you've created

**Formula syntax tips:**
- Use underscores for column names with spaces: `Monthly_ROI_Goal`
- Add `+ 1` or `+ 0.01` to avoid division by zero
- Use parentheses for order of operations
- Example: `(usage_last_30_days * 100) / (Investment + 1)`

### 3. Column Visibility
**Purpose:** Choose which columns appear in the Portfolio Overview table

**How to use:**
1. Go to Settings tab
2. Scroll to "Column Visibility"
3. Select/deselect columns from the multiselect
4. Click "Save Column Visibility"
5. Return to Portfolio Overview to see changes

## Tips

- All settings are saved to `custom_columns_config.json`
- Changes take effect immediately after saving
- Custom columns appear in all exports and views
- Calculated columns automatically update when data changes
- You can delete columns anytime (data is preserved in config)

## Troubleshooting

**Calculated column shows error:**
- Check formula syntax
- Make sure column names match exactly (check for spaces/underscores)
- Verify all referenced columns exist

**Data column values not saving:**
- Make sure to click "Save Changes" after editing
- Refresh the page if changes don't appear

**Column not appearing in table:**
- Check Column Visibility settings
- Make sure column was added successfully
