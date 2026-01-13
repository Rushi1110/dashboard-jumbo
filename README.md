🚀 Quick Start
Requirements: pip install streamlit pandas plotly numpy

Execution: streamlit run app.py

Data Updates: Simply replace the CSV files in the root folder with the latest exports.

📁 Required Data Files
Owners.csv: Owner lead generation and status tracking.

Visits.csv: The source for lead owner points and visit metrics.

Buyers.csv: Buyer lead counts and demand price preferences.

Homes.csv: Inventory status (Live/On Hold/Sold) and "Regrettable Loss" values.

home_inspection.csv: VA performance tracking for property inspections.

home_catalogue.csv: Media verification (Floor plan "https" check).

price-history-new.csv: MTD vs MTD-1 price revision analysis.

offers.csv: Offer volume and status tracking.

Admins.csv: Master mapping for Name ↔ Email and team roles.

🧠 Core Dashboard Logic
Lead Owner Points: 3 pts for a new visitor; 7 pts for a Repeat Visitor (RV).

VA Points: 4 pts per Managed Visit; 4 pts per Inspection.

Repeat Visitor (RV): Defined as a phone number with a completed visit prior to the selected start date or multiple visit dates within the range.

SKU Floor Plans: Only counts if the value is non-null and contains "https".

Top Projects: Calculated by splitting the Homes_Visited string to extract the building name.

Comparison Delta: Every metric calculates the % increase/decrease by comparing the selected range to the identical number of days immediately preceding it.

⚙️ Admin Controls
Manual Overrides: Use the Admin Tab in the UI to input points for Tours (20 pts) and Google Ratings (10 pts) per person.

Name Mapping: If names appear as "Unknown," verify the user's email is correctly mapped in Admins.csv.
