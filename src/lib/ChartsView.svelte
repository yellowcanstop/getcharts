<script lang="ts">
  import { onMount } from 'svelte';
  import { dbManager } from './db.svelte';
  import Plotly from 'plotly.js-dist-min';
  import { ChartType, type ChartView } from './types';

  let error = $state("");
  let chartsContainer: HTMLDivElement;

  onMount(async () => {
    try {
      await dbManager.generateRecommendations();
      renderCharts();
    } catch (e: any) {
      error = "Failed to generate charts: " + e.message;
    }
  });

  /*
  function renderChart(element: HTMLDivElement, view: ChartView) {
    const data = createPlotlyData(view);
    const layout = createPlotlyLayout(view);
    Plotly.newPlot(element, data, layout, { responsive: true });
    return {
      destroy() {
        Plotly.purge(element);
      }
    }
  }
  */

  
  function renderCharts() {
    if (!chartsContainer) return;
    
    // Clear previous charts
    chartsContainer.innerHTML = '';
    
    if (dbManager.recommendedCharts.length === 0) {
      chartsContainer.innerHTML = '<p class="no-charts">No charts were generated. Try a different dataset.</p>';
      return;
    }

    dbManager.recommendedCharts.forEach((view, index) => {
      const chartDiv = document.createElement('div');
      chartDiv.className = 'chart-item';
      chartsContainer.appendChild(chartDiv);

      const data = createPlotlyData(view);
      const layout = createPlotlyLayout(view);
      
      Plotly.newPlot(chartDiv, data, layout, { responsive: true });
    });
  }
  

  function createPlotlyData(view: ChartView) {
    const { X, Y, chartType, xName, yName } = view;

    switch (chartType) {
      case ChartType.SCATTER:
        return [{
          x: X[0],
          y: Y[0],
          mode: 'markers',
          type: 'scatter',
          marker: { size: 8, color: 'rgba(55, 128, 191, 0.7)' },
          name: yName
        }];

      case ChartType.LINE:
        return [{
          x: X[0],
          y: Y[0],
          mode: 'lines+markers',
          type: 'scatter',
          line: { color: 'rgba(55, 128, 191, 0.9)', width: 2 },
          marker: { size: 6 },
          name: yName
        }];

      case ChartType.BAR:
        return [{
          x: X[0],
          y: Y[0],
          type: 'bar',
          marker: { color: 'rgba(55, 128, 191, 0.7)' },
          name: yName
        }];

      case ChartType.PIE:
        return [{
          labels: X[0],
          values: Y[0],
          type: 'pie',
          marker: {
            colors: [
              'rgba(55, 128, 191, 0.9)',
              'rgba(219, 64, 82, 0.9)',
              'rgba(128, 177, 211, 0.9)',
              'rgba(255, 127, 14, 0.9)',
              'rgba(44, 160, 44, 0.9)'
            ]
          }
        }];

      default:
        return [];
    }
  }

  function createPlotlyLayout(view: any) {
    const { xName, yName, chartType, score } = view;
    
    const chartTypeNames = ['Scatter Plot', 'Line Chart', 'Bar Chart', 'Pie Chart'];
    const typeLabel = chartTypeNames[chartType] || 'Chart';
    const titleText = `<b>${typeLabel}</b>: ${xName} vs ${yName}<br><span style="font-size: 12px; color: #666;">Score: ${score.toFixed(2)}</span>`;
    //const title = `${chartTypeNames[chartType]}: ${xName} vs ${yName}<br><sub>Score: ${score.toFixed(2)}</sub>`;

    // Base layout configuration
    const layout: any = {
      // 1. Use the Object format for title (highly recommended)
      title: {
        text: titleText,
        font: {
          family: 'Arial, sans-serif',
          size: 16,
          color: '#333'
        },
        x: 0.05,
        xanchor: 'left',
        pad: { t: 10 }
      },
// 2. Explicitly increase the top margin (t) to prevent clipping
      margin: {
        t: 100, // Increased to 100px to fit two lines of text
        b: 60,
        l: 60,
        r: 40
      },
      height: 450, // Slightly taller to account for the extra margin
      autosize: true,
      showlegend: chartType === ChartType.PIE
    };

    // 3. Add axes labels for non-pie charts
    if (chartType !== ChartType.PIE) {
      layout.xaxis = { title: { text: xName, standoff: 15 } };
      layout.yaxis = { title: { text: yName, standoff: 15 } };
    }

    /*
    if (chartType === ChartType.PIE) {
      return {
        title,
        showlegend: true,
        height: 400
      };
    }

    return {
      title,
      xaxis: { title: xName },
      yaxis: { title: yName },
      showlegend: false,
      height: 400
    };
    */
   return layout;
  }

  function handleReset() {
    dbManager.reset();
  }
</script>

<div class="charts-view">
  <div class="header">
    <h2>Recommended Charts</h2>
    <button onclick={handleReset} class="reset-btn">Upload New File</button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if dbManager.isGenerating}
    <p class="loading">Analyzing data and generating charts...</p>
  {:else if dbManager.recommendedCharts.length === 0}
    <p class="no-charts">No charts were generated. Try a different dataset.</p>
  {:else}
    <div bind:this={chartsContainer} class="charts-container"></div>
  {/if}
</div>

<style>
  .charts-view {
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
  }

  .header h2 {
    margin: 0;
    font-size: 1.8rem;
    color: #333;
  }

  .reset-btn {
    padding: 10px 20px;
    background-color: #3778bf;
    color: white;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 1rem;
    transition: background-color 0.2s;
  }

  .reset-btn:hover {
    background-color: #2a5d99;
  }

  .error {
    color: #d32f2f;
    padding: 15px;
    background-color: #ffebee;
    border-radius: 5px;
    margin: 20px 0;
  }

  .loading {
    text-align: center;
    font-size: 1.2rem;
    color: #666;
    padding: 40px;
  }

  .no-charts {
    text-align: center;
    color: #666;
    padding: 40px;
    font-size: 1.1rem;
  }

  .charts-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
    gap: 30px;
    margin-top: 20px;
  }

  :global(.chart-item) {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 15px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    min-height: 480px;
  }

  @media (max-width: 768px) {
    .charts-container {
      grid-template-columns: 1fr;
    }

    .header {
      flex-direction: column;
      align-items: flex-start;
      gap: 15px;
    }
  }
</style>