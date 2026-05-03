"""Generate index.html for the static site.

Creates an index page that links to all available forecast reports.
"""

import os
import sys
from datetime import date
from pathlib import Path


def generate_index(output_dir: Path) -> str:
    """Generate an index.html page linking to all forecast files.
    
    Args:
        output_dir: Root output directory containing location subdirs
        
    Returns:
        HTML content for the index page
    """
    today = date.today()
    
    lines = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "  <meta charset=\"UTF-8\">",
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        "  <title>BBC Weather Forecasts</title>",
        "  <style>",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
        "           max-width: 800px; margin: 50px auto; padding: 20px;",
        "           background: #f5f5f5; }",
        "    h1 { color: #333; }",
        "    .location { margin: 30px 0; padding: 20px; background: white;",
        "                border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        "    .location h2 { margin-top: 0; color: #222; }",
        "    .reports { list-style: none; padding: 0; }",
        "    .reports li { padding: 8px 0; border-bottom: 1px solid #eee; }",
        "    .reports li:last-child { border-bottom: none; }",
        "    .reports a { color: #0066cc; text-decoration: none; }",
        "    .reports a:hover { text-decoration: underline; }",
        "    .meta { color: #666; font-size: 0.9em; margin-top: 10px; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <h1>BBC Weather Forecasts</h1>",
        "  <p>Generated: " + today.strftime("%Y-%m-%d") + "</p>",
    ]
    
    if not output_dir.exists():
        return "\n".join(lines + ["  <p>No forecast data available.</p>", "</body>", "</html>"])
    
    location_dirs = sorted(output_dir.iterdir())
    
    if not location_dirs:
        lines.append("  <p>No forecast data available.</p>")
    else:
        for loc_dir in location_dirs:
            if not loc_dir.is_dir():
                continue
            
            # Extract location ID from dir name (e.g., "BBC Weather location 2644577")
            location_id = loc_dir.name.replace("BBC Weather location ", "")
            
            lines.append(f"  <div class=\"location\">")
            lines.append(f"    <h2>BBC Weather Location {location_id}</h2>")
            lines.append("    <ul class=\"reports\">")
            
            # Find all forecast files
            for md_file in sorted(loc_dir.glob("*.md")):
                lines.append(f"      <li><a href=\"{loc_dir.name}/{md_file.name}\">{md_file.name}</a></li>")
            
            lines.append("    </ul>")
            lines.append("  </div>")
    
    lines.extend([
        "  <div class=\"meta\">",
        "    <p>Weather data from BBC Weather. Updated every [minimum GitHub Actions workflow interval - currently 2 hours as of last edit to this page template].</p>",
        "  </div>",
        "</body>",
        "</html>"
    ])
    
    return "\n".join(lines)


def main():
    output_dir = Path(os.environ.get("WEATHER_BATCH_OUTPUT", "output"))
    
    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    
    html = generate_index(output_dir)
    
    # Write to output_dir/index.html
    index_path = output_dir / "index.html"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(html)
    print(f"Generated {index_path}")


if __name__ == "__main__":
    main()
