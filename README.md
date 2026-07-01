# Plotly MCP Server

A Model Context Protocol (MCP) server that provides powerful data visualization capabilities using Plotly. This server enables AI assistants to generate interactive charts, graphs, and plots from data through standardized MCP tools.

## Overview

This MCP server implements a comprehensive data visualization toolkit using FastMCP and Plotly Express. It provides multiple specialized tools for creating various chart types with flexible data input options, supporting everything from simple scatter plots to complex scatter matrices and density heatmaps.

### Key Features

- **Multiple Chart Types**: Support for 11 different chart types including scatter, line, bar, histogram, box, violin, pie, heatmap, area, density heatmap, and scatter matrix
- **Flexible Data Input**: Accept data as dictionaries, lists of rows, or JSON strings
- **Multiple Output Formats**: Export charts as HTML (interactive), PNG (raster), or SVG (vector)
- **Theme Support**: 11 built-in Plotly themes for consistent styling
- **Smart Column Inference**: Automatically detects and uses appropriate columns when not specified
- **Specialized Tools**: Individual tools for each chart type with optimized parameters
- **Chart Suggestions**: AI-powered chart type recommendations based on data structure
- **Database Integration Ready**: Designed to work seamlessly with SQL/semantic search MCP servers

## How MCP Works with This Server

This server implements the Model Context Protocol (MCP) standard using FastMCP. Here's how it integrates into your AI workflow:

### MCP Architecture

```
AI Assistant (Claude, Devin, etc.)
    ↓
MCP Client (built into AI platform)
    ↓
MCP Server (this Plotly server)
    ↓
Plotly Express + Pandas
    ↓
Chart Output (HTML/PNG/SVG)
```

### Communication Flow

1. **Tool Discovery**: The MCP client queries this server for available tools using the `list_tools` method
2. **Tool Invocation**: AI assistants call specific tools (e.g., `create_chart`) with structured parameters
3. **Data Processing**: The server processes input data, validates parameters, and generates charts
4. **Response Return**: Charts are returned as base64-encoded data or file paths with metadata

### Integration with Other MCP Servers

This server is designed to work in conjunction with other MCP servers:

```
Semantic Search/SQL MCP Server
    ↓ (query results)
Plotly MCP Server (this)
    ↓ (charts)
AI Assistant (displays to user)
```
## Authentication
## Connect to This MCP Server

**Important**: This MCP server is currently not public. To get authenticated and access the server, please email:

**sarthak.jain854@gmail.com**

This server is live and remotely accessible at:

**`https://plotly-mcp.fastmcp.app/mcp`**

No installation needed — just point any MCP-compatible client at this URL using the **Streamable HTTP** transport.

### Claude Code

```bash
claude mcp add --transport http plotly-mcp https://plotly-mcp.fastmcp.app/mcp
```

Then verify it's connected:
```bash
claude
/mcp
```

### Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "plotly-mcp": {
      "url": "https://plotly-mcp.fastmcp.app/mcp",
      "transport": "http"
    }
  }
}
```
Restart Claude Desktop after saving.

### Cursor

Add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "plotly-mcp": {
      "url": "https://plotly-mcp.fastmcp.app/mcp",
      "transport": "http"
    }
  }
}
```

### Codex CLI

```bash
codex mcp add --url https://plotly-mcp.fastmcp.app/mcp plotly-mcp
```

### Gemini CLI

```bash
gemini mcp add plotly-mcp https://plotly-mcp.fastmcp.app/mcp --transport http
```

### Any other MCP client (generic config)

Most MCP clients accept a JSON config in this shape — swap in your client's expected key names if they differ:

```json
{
  "mcpServers": {
    "plotly-mcp": {
      "url": "https://plotly-mcp.fastmcp.app/mcp",
      "transport": "http"
    }
  }
}
```

### Using the FastMCP Python client directly

```python
from fastmcp import Client
import asyncio

async def main():
    async with Client("https://plotly-mcp.fastmcp.app/mcp") as client:
        tools = await client.list_tools()
        print(tools)

asyncio.run(main())
```

The server includes a **precontext prompt** that guides AI assistants through the proper workflow:

1. Use Semantic Search/SQL MCP first to run queries and fetch result rows
2. Transform DB rows into Plotly tool input payloads
3. Use Plotly MCP tools to generate charts
4. Save the generated chart to a local file
5. Show the saved chart in the chat UI as an image
6. Automatically open the chart file for immediate viewing

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- Virtual environment (recommended)

### Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd plotly-server
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Verify installation**:
   ```bash
   python server.py --help
   ```

### Dependencies

Key dependencies include:
- `fastmcp` - MCP server framework
- `plotly` - Interactive plotting library
- `pandas` - Data manipulation
- `pydantic` - Data validation
- `kaleido` - Required for PNG/SVG export (if needed)


## Available Tools

### Core Chart Tools

#### 1. `create_chart` - Universal Chart Creator

The main tool for creating any supported chart type with maximum flexibility.

**Parameters:**
- `chart_type` (required): Chart type - "scatter", "line", "bar", "histogram", "box", "violin", "pie", "heatmap", "area", "density_heatmap", "scatter_matrix"
- `data` (required): Data as dict, list of rows, or JSON string
- `title` (optional): Chart title (default: "Chart")
- `x_column` (optional): Column name for x-axis (auto-detected if not provided)
- `y_column` (optional): Column name for y-axis (auto-detected if not provided)
- `x_title` (optional): X-axis label (default: "")
- `y_title` (optional): Y-axis label (default: "")
- `output_format` (optional): "html", "png", or "svg" (default: "html")
- `output_file` (optional): File path to save the chart
- `theme` (optional): Chart theme (default: "plotly")
- `width` (optional): Chart width in pixels, 100-2000 (default: 800)
- `height` (optional): Chart height in pixels, 100-2000 (default: 600)

**Example Usage:**
```python
# With database query results
data = {
    "rows": [
        {"category": "A", "value": 10},
        {"category": "B", "value": 20},
        {"category": "C", "value": 15}
    ]
}
create_chart(
    chart_type="bar",
    data=data,
    title="Sales by Category",
    x_column="category",
    y_column="value"
)
```

#### 2. `create_scatter_plot` - Scatter Plot Specialist

Specialized tool for scatter plots with support for colors, sizes, and labels.

**Parameters:**
- `x_data`, `y_data`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names for DataFrame input
- `color_column`, `size_column`, `label_column`: Additional dimensions
- `colors`, `sizes`, `labels`: Direct data for additional dimensions
- `title`, `x_title`, `y_title`: Chart labels
- `output_format`, `output_file`: Output configuration

**Best For:** Correlation analysis, clustering visualization, multi-dimensional data

#### 3. `create_bar_chart` - Bar Chart Specialist

Optimized for categorical data comparison with orientation control.

**Parameters:**
- `categories`, `values`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- `orientation`: "vertical" or "horizontal" (default: "vertical")
- Standard label and output parameters

**Best For:** Categorical comparisons, rankings, frequency distributions

#### 4. `create_line_chart` - Line Chart Specialist

Designed for time series and trend visualization.

**Parameters:**
- `x_data`, `y_data`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- `line_name`: Series name for legend
- Standard label and output parameters

**Best For:** Time series, trends, sequential data

#### 5. `create_histogram_chart` - Distribution Analysis

Specialized for distribution analysis and frequency visualization.

**Parameters:**
- `values`: Direct data list for distribution
- `data`: Alternative: DataFrame/rows input
- `x_column`: Column name for DataFrame input
- Standard label and output parameters

**Best For:** Distribution analysis, frequency counts, data exploration

#### 6. `create_box_plot` - Statistical Analysis

Box plots for spread, quartiles, and outlier analysis.

**Parameters:**
- `categories`, `values`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- Standard label and output parameters

**Best For:** Statistical summary, outlier detection, group comparisons

#### 7. `create_violin_plot` - Distribution Shape

Violin plots for showing distribution shape across groups.

**Parameters:**
- `categories`, `values`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- Standard label and output parameters

**Best For:** Distribution shape comparison, density visualization

#### 8. `create_pie_chart` - Composition Analysis

Pie charts for showing part-to-whole relationships.

**Parameters:**
- `labels`, `values`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- Standard label and output parameters

**Best For:** Composition analysis, percentage breakdowns, categorical proportions

#### 9. `create_area_chart` - Cumulative Trends

Area charts for cumulative trend visualization.

**Parameters:**
- `x_data`, `y_data`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- Standard label and output parameters

**Best For:** Cumulative trends, volume over time, part-to-whole over time

#### 10. `create_density_heatmap` - Density Visualization

Density heatmaps for showing concentrated regions in bivariate data.

**Parameters:**
- `x_data`, `y_data`: Direct data lists
- `data`: Alternative: DataFrame/rows input
- `x_column`, `y_column`: Column names
- Standard label and output parameters

**Best For:** Density analysis, hotspot identification, 2D distribution

#### 11. `create_scatter_matrix` - Multi-variable Analysis

Scatter matrices for exploring correlations between multiple variables.

**Parameters:**
- `data` (required): DataFrame/rows input
- `dimensions`: List of column names to include (auto-detected if not provided)
- Standard label and output parameters

**Best For:** Multi-variable correlation analysis, feature exploration

### Utility Tools

#### 12. `get_supported_charts` - Feature Information

Returns comprehensive information about supported features, chart types, formats, and themes.

**Returns:** JSON with:
- Supported chart types
- Output formats
- Available themes
- Feature descriptions
- Specialized tools list
- Precontext prompt
- Schema playbook

**Usage:**
```python
get_supported_charts()
```

#### 13. `suggest_chart_from_data` - AI-Powered Recommendations

Analyzes data structure and suggests the most appropriate chart type and column mapping.

**Parameters:**
- `data` (required): Data to analyze
- `user_question` (optional): Context about what the user wants to visualize

**Returns:** JSON with:
- Suggested chart type
- Column mapping
- Reasoning for the suggestion
- Recommended next step

**Usage:**
```python
suggest_chart_from_data(
    data={"rows": [{"status": "complete", "count": 5}, ...]},
    user_question="How many tasks in each status?"
)
```

## Data Input Formats

The server supports multiple flexible data input formats:

### 1. List of Rows (Recommended for Database Results)
```python
data = {
    "rows": [
        {"category": "A", "value": 10, "metadata": "x"},
        {"category": "B", "value": 20, "metadata": "y"},
        {"category": "C", "value": 15, "metadata": "z"}
    ]
}
```

### 2. Direct X/Y Arrays
```python
data = {
    "x": [1, 2, 3, 4, 5],
    "y": [10, 20, 15, 25, 30]
}
```

### 3. JSON String
```python
data = '{"rows": [{"category": "A", "value": 10}]}'
```

### 4. Pie Chart Specific
```python
data = {
    "labels": ["A", "B", "C"],
    "values": [10, 20, 15]
}
```

### 5. Heatmap Specific
```python
data = {
    "z_values": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
}
```

## Supported Chart Types

| Chart Type | Best For | Input Requirements |
|------------|----------|-------------------|
| **scatter** | Correlation analysis, clustering | x, y coordinates |
| **line** | Time series, trends | Sequential x, y data |
| **bar** | Categorical comparison | Categories, values |
| **histogram** | Distribution analysis | Single variable values |
| **box** | Statistical summary, outliers | Categories, values |
| **violin** | Distribution shapes | Categories, values |
| **pie** | Composition analysis | Labels, values |
| **heatmap** | Matrix data, intensity | 2D array or pivoted table |
| **area** | Cumulative trends | x, y coordinates |
| **density_heatmap** | Density concentration | x, y coordinates |
| **scatter_matrix** | Multi-variable correlation | Multiple numeric columns |

## Output Formats

### HTML (Default)
- **Description**: Interactive HTML with Plotly.js
- **Features**: Zoom, pan, hover tooltips, legend toggling
- **File Size**: Medium (~50-200 KB)
- **Best For**: Web applications, interactive exploration

### PNG
- **Description**: High-quality raster image
- **Features**: Static image, no interactivity
- **File Size**: Small (~20-100 KB)
- **Requirements**: Kaleido package
- **Best For**: Documents, presentations, print materials

### SVG
- **Description**: Scalable vector graphics
- **Features**: Crisp at any size, editable
- **File Size**: Very small (~5-30 KB)
- **Requirements**: Kaleido package
- **Best For**: Web graphics, logos, print materials

## Themes

The server supports 11 built-in Plotly themes:

- **plotly**: Default Plotly theme
- **plotly_white**: Light theme with white background
- **plotly_dark**: Dark theme for dark backgrounds
- **ggplot2**: R ggplot2 style
- **seaborn**: Python seaborn style
- **simple_white**: Minimalist white theme
- **presentation**: Optimized for presentations
- **xgridoff**: Hide vertical grid lines
- **ygridoff**: Hide horizontal grid lines
- **gridon**: Show all grid lines
- **none**: No theme styling

## Schema Playbook

The server includes a built-in schema playbook for common database visualization scenarios:

### Sample Tables
- **projects**: Project management data
- **task**: Task tracking with status and priority
- **subtasks**: Subtask details with time tracking
- **goals**: Goal ownership and tracking
- **comments**: Comment metadata
- **task_updates**: Task update history

### Recommended Query Patterns

The playbook includes pre-built query + chart combinations:

1. **Task Status Distribution**
   - SQL: `SELECT status, COUNT(*) AS task_count FROM task GROUP BY status`
   - Chart: Bar or Pie chart

2. **Project Task Counts**
   - SQL: `SELECT p.name AS project_name, COUNT(t.id) AS task_count FROM projects p LEFT JOIN task t ON p.id = t.projectId GROUP BY project_name`
   - Chart: Bar chart

3. **Progress by Priority**
   - SQL: `SELECT priority, progress FROM task WHERE progress IS NOT NULL`
   - Chart: Box plot

4. **Updates Over Time**
   - SQL: `SELECT DATE_TRUNC('month', createdAt)::date AS update_month, COUNT(*) AS updates FROM task_updates GROUP BY update_month`
   - Chart: Line chart

## Usage Examples

### Example 1: Basic Bar Chart from Lists
```python
from plotly_server import create_chart

data = {
    "rows": [
        {"product": "A", "sales": 100},
        {"product": "B", "sales": 150},
        {"product": "C", "sales": 120}
    ]
}

result = create_chart(
    chart_type="bar",
    data=data,
    title="Sales by Product",
    x_column="product",
    y_column="sales",
    output_format="html"
)
```

### Example 2: Scatter Plot with Colors
```python
from plotly_server import create_scatter_plot

data = {
    "rows": [
        {"x": 1, "y": 10, "category": "A"},
        {"x": 2, "y": 15, "category": "B"},
        {"x": 3, "y": 8, "category": "A"},
        {"x": 4, "y": 20, "category": "B"}
    ]
}

result = create_scatter_plot(
    data=data,
    x_column="x",
    y_column="y",
    color_column="category",
    title="Correlation Analysis"
)
```

### Example 3: Time Series Line Chart
```python
from plotly_server import create_line_chart

data = {
    "rows": [
        {"date": "2024-01", "value": 100},
        {"date": "2024-02", "value": 120},
        {"date": "2024-03", "value": 115},
        {"date": "2024-04", "value": 140}
    ]
}

result = create_line_chart(
    data=data,
    x_column="date",
    y_column="value",
    title="Monthly Trend",
    x_title="Month",
    y_title="Value"
)
```

### Example 4: AI-Powered Chart Suggestion
```python
from plotly_server import suggest_chart_from_data

data = {
    "rows": [
        {"status": "complete", "count": 25},
        {"status": "in_progress", "count": 15},
        {"status": "pending", "count": 10}
    ]
}

suggestion = suggest_chart_from_data(
    data=data,
    user_question="What's the task status breakdown?"
)

# Returns recommended chart type and mapping
```

### Example 5: Export to PNG
```python
from plotly_server import create_chart

result = create_chart(
    chart_type="pie",
    data={"labels": ["A", "B", "C"], "values": [10, 20, 15]},
    title="Distribution",
    output_format="png",
    output_file="chart.png"
)
```

## Integration Examples

### With SQL MCP Server

```python
# 1. Query database via SQL MCP
query_result = sql_mcp.execute_query("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")

# 2. Transform to Plotly format
plotly_data = {"rows": query_result.rows}

# 3. Create chart
chart = create_chart(
    chart_type="bar",
    data=plotly_data,
    x_column="status",
    y_column="count"
)

# 4. Save and display
save_chart(chart, "task_status.png")
display_image("task_status.png")
```

### With Semantic Search MCP

```python
# 1. Semantic search for data
search_results = semantic_mcp.search("task progress by priority")

# 2. Extract and transform data
plotly_data = {"rows": search_results.data}

# 3. Get chart suggestion
suggestion = suggest_chart_from_data(plotly_data, "task progress analysis")

# 4. Create suggested chart
chart = create_chart(
    chart_type=suggestion.chart_type,
    data=plotly_data,
    **suggestion.mapping
)
```

## Architecture Details

### Component Structure

```
server.py
├── FastMCP Initialization
├── Constants & Configuration
│   ├── SUPPORTED_CHARTS
│   ├── SUPPORTED_FORMATS
│   ├── SUPPORTED_THEMES
│   ├── PRECONTEXT_PROMPT
│   └── SCHEMA_PLAYBOOK
├── Helper Functions
│   ├── _normalize_data() - Data format normalization
│   ├── _data_to_dataframe() - Convert to pandas DataFrame
│   ├── _build_figure() - Core chart building logic
│   ├── _format_output() - Output formatting
│   ├── _build_axis_metadata() - Metadata generation
│   └── _infer_chart_type_from_rows() - AI chart inference
├── MCP Tools (decorated with @mcp.tool())
│   ├── create_chart() - Universal chart creator
│   ├── create_scatter_plot() - Scatter specialist
│   ├── create_bar_chart() - Bar specialist
│   ├── create_line_chart() - Line specialist
│   ├── create_histogram_chart() - Histogram specialist
│   ├── create_box_plot() - Box plot specialist
│   ├── create_violin_plot() - Violin specialist
│   ├── create_pie_chart() - Pie specialist
│   ├── create_area_chart() - Area specialist
│   ├── create_density_heatmap() - Density heatmap specialist
│   ├── create_scatter_matrix() - Scatter matrix specialist
│   ├── get_supported_charts() - Feature information
│   └── suggest_chart_from_data() - AI recommendations
└── Server Entry Point
```

### Data Flow

```
User/AI Request
    ↓
MCP Tool Call
    ↓
Data Normalization (_normalize_data)
    ↓
DataFrame Conversion (_data_to_dataframe)
    ↓
Figure Building (_build_figure)
    ↓
Plotly Express Chart Generation
    ↓
Metadata Building (_build_axis_metadata)
    ↓
Output Formatting (_format_output)
    ↓
Base64 Encoding / File Saving
    ↓
Response with Metadata
```

## Error Handling

The server includes comprehensive error handling:

- **Invalid Chart Types**: Returns clear error message with supported types
- **Missing Data**: Validates required data fields
- **Column Mismatch**: Provides helpful messages about available columns
- **Theme Errors**: Validates theme names against supported list
- **File Errors**: Handles file system permissions and paths

## Performance Considerations

- **Data Size**: Optimized for datasets up to ~10,000 rows
- **Large Datasets**: Consider aggregating before visualization
- **Image Export**: PNG/SVG export requires Kaleido and may be slower
- **Memory Usage**: Uses pandas for efficient data manipulation

## Troubleshooting

### Common Issues

**Issue**: "Kaleido not found" error
- **Solution**: Install kaleido: `pip install kaleido`

**Issue**: Charts not displaying in chat
- **Solution**: Ensure output_format is "html" for interactive charts

**Issue**: Column auto-detection not working
- **Solution**: Explicitly specify x_column and y_column parameters

**Issue**: Theme not applying
- **Solution**: Verify theme name against get_supported_charts() output

### Debug Mode

Enable verbose logging by setting environment variable:
```bash
export DEBUG=true
python server.py
```

## Contributing

Contributions are welcome! Areas for improvement:

- Additional chart types (3D plots, geographic charts)
- Custom theme support
- Animation capabilities
- Real-time data streaming
- Additional export formats (PDF, etc.)
- Performance optimizations for large datasets

## License

[Specify your license here]

## Support

For issues, questions, or contributions:
- GitHub Issues: [https://github.com/Sarthakiameya/PlotlyMCP]
- email: [sarthak.jain854@gmail.com]
- MCP Specification: https://modelcontextprotocol.io

## Acknowledgments

Built with:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP Server Framework
- [Plotly](https://plotly.com/) - Interactive Plotting Library
- [Pandas](https://pandas.pydata.org/) - Data Manipulation
- [Model Context Protocol](https://modelcontextprotocol.io/) - Protocol Specification
