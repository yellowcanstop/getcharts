<script lang="ts">
  import { onMount } from 'svelte';
  import { dbManager } from './db.svelte';
  import Plotly from 'plotly.js-dist-min';
  import { ChartType, ColumnType, type ChartView } from './types';

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
  
  function renderCharts() {
    if (!chartsContainer) return;
    
    chartsContainer.innerHTML = '';
    
    if (dbManager.recommendedCharts.length === 0) {
      chartsContainer.innerHTML = '<p class="no-charts">No charts were generated. Try a different dataset.</p>';
      return;
    }

    dbManager.recommendedCharts.forEach(view => {
      const chartDiv = document.createElement('div');
      chartDiv.className = 'chart-item';
      //const viewDiv = document.createElement('pre');
      //viewDiv.textContent = JSON.stringify(view, null, 2);
      chartsContainer.appendChild(chartDiv);
      //chartsContainer.appendChild(viewDiv);

      const data = createPlotlyData(view);
      const layout = createPlotlyLayout(view);
      
      Plotly.newPlot(chartDiv, data, layout, { responsive: true });
    });
  }
  
  function createPlotlyData(view: ChartView) {
    const { X, Y, chartType, seriesNum, seriesNames, xFeature } = view;

    // multi-series charts
    if (seriesNum > 1) {
      const traces = [];
      for (let i = 0; i < seriesNum; i++) {
        traces.push({
          x: X[i],
          y: Y[i],
          type: chartType === ChartType.LINE ? 'line' : 'bar',
          mode: chartType === ChartType.LINE ? 'lines' : undefined,
          name: seriesNames?.[i] || `Series ${i + 1}`,
        });
      }
      return traces;
    }

    switch (chartType) {
      case ChartType.SCATTER:
        return [{
          x: X[0],
          y: Y[0],
          mode: 'markers',
          type: 'scatter',
        }];
      case ChartType.LINE:
        return [{
          x: X[0],
          y: Y[0],
          mode: 'lines',
          type: 'line',
        }];
      case ChartType.BAR:
        return [{
          x: X[0],
          y: Y[0],
          type: 'bar',
        }];
      case ChartType.PIE:
        return [{
          labels: X[0],
          values: Y[0],
          type: 'pie',
        }];
      default:
        return [];
    }
  }

  function createPlotlyLayout(view: any) {
    const { xName, yName, chartType, score, description, seriesNum } = view;
    
    const chartTypeNames = ['Scatter Plot', 'Line Chart', 'Bar Chart', 'Pie Chart'];
    const typeLabel = chartTypeNames[chartType] || 'Chart';
    const titleText = `<b>${typeLabel}</b>: ${description}<br><span style="font-size: 12px; color: #666;">Score: ${score.toFixed(2)}</span>`;
   
    const layout: any = {
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
      margin: {
        t: 100, 
        b: 60,
        l: 60,
        r: 40
      },
      height: 450, 
      autosize: true,
      showlegend: chartType === ChartType.PIE || seriesNum > 1
    };

    if (chartType === ChartType.BAR && seriesNum > 1) {
      layout.barmode = 'group';
    }

    if (chartType !== ChartType.PIE) {
      layout.xaxis = { title: { text: xName, standoff: 15 } };
      layout.yaxis = { title: { text: yName, standoff: 15 } };
    }

    if ((chartType === ChartType.LINE || chartType === ChartType.BAR) && view.xFeature.type === ColumnType.TEMPORAL) {
      layout.xaxis = { type: 'date' };
    }

   return layout;
  }

  function handleReset() {
    dbManager.reset();
    error = "";
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