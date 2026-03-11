<script lang="ts">
  import { onMount } from 'svelte';
  import { dbManager } from './db.svelte';
  import Plotly from 'plotly.js-dist-min';
  import { ChartType, ColumnType, type ChartView } from './types';

  let error = $state("");
  let selectedChart = $state<ChartView | null>(null);

  onMount(async () => {
    try {
      await dbManager.generateRecommendations();
    } catch (e: any) {
      error = "Failed to generate charts: " + e.message;
    }
  });

  // Svelte 'Action' to initialize Plotly on the element.
  // Runs when the element enters the DOM.
  function plotlyAction(node: HTMLElement, { view, isLarge }: { view: ChartView, isLarge: boolean }) {
    const data = createPlotlyData(view);
    const layout = createPlotlyLayout(view, isLarge);
    
    Plotly.newPlot(node, data, layout, { 
      responsive: true,
      displayModeBar: isLarge
    });

    return {
      destroy() {
        Plotly.purge(node);
      }
    };
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

  function createPlotlyLayout(view: any, isLarge: boolean) {
    const { xName, yName, chartType, score, description, seriesNum } = view;
    
    const chartTypeNames = ['Scatter Plot', 'Line Chart', 'Bar Chart', 'Pie Chart'];
    const typeLabel = chartTypeNames[chartType] || 'Chart';
    const titleText = `<b>${typeLabel}</b>: ${description}<br><span style="font-size: 12px; color: #666;">Score: ${score.toFixed(2)}</span>`;
    const fontSize = isLarge ? 12 : 8;      
    const labelSize = isLarge ? 14 : 8;    
    const titleSize = isLarge ? 14 : 9;
   
    const layout: any = {
      title: {
        text: isLarge ? titleText : '',
        font: {
          family: 'Arial, sans-serif',
          size: titleSize,
          color: '#333'
        },
        x: 0.05,
        xanchor: 'left',
        pad: { t: 10 }
      },
      margin: isLarge? {
        t: 80, 
        b: 60,
        l: 60,
        r: 40
      } : {
        t: 10,
        b: 10,
        l: 10,
        r: 10
      },
      height: isLarge? 400 : 150, 
      width: isLarge? 600 : 300,
      autosize: true,
      showlegend: isLarge && (chartType === ChartType.PIE || seriesNum > 1),
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
    };

    if (chartType === ChartType.BAR && seriesNum > 1) {
      layout.barmode = 'group';
    }

    if (chartType !== ChartType.PIE) {
      layout.xaxis = { 
        title: { 
          text: xName, 
          font: { size: labelSize },
          standoff: 15 
        },
        tickfont: { size: fontSize },
        automargin: true
      };
      layout.yaxis = { 
        title: { 
          text: yName,
          font: { size: labelSize },
          standoff: 15 
        },
        tickfont: { size: fontSize },
        automargin: true
      };
    }

    if ((chartType === ChartType.LINE || chartType === ChartType.BAR) && view.xFeature.type === ColumnType.TEMPORAL) {
      layout.xaxis = { 
        type: 'date',
        title: { 
          text: xName, 
          font: { size: labelSize },
          standoff: 15 
        },
        tickfont: { size: fontSize },
        automargin: true 
      };
    }

    if (chartType === ChartType.BAR) {
      layout.yaxis = {
        title: { 
          text: yName,
          font: { size: labelSize },
          standoff: 15 
        },
        tickfont: { size: fontSize },
        automargin: true,
        rangemode: 'tozero'
      };
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
    <div class="charts-grid">
      {#each dbManager.recommendedCharts as view}
        <button class="chart-card" onclick={() => selectedChart = view}>
          <div use:plotlyAction={{ view, isLarge: false }}></div>
          <p class="chart-label">{view.description}</p>
        </button>
      {/each}
    </div>
  {/if}

  {#if selectedChart}
    <div class="modal-backdrop" onclick={() => selectedChart = null} aria-hidden="true">
      <div class="modal-content" onclick={(e) => e.stopPropagation()} aria-hidden="true">
        <button class="close-btn" onclick={() => selectedChart = null}>✕</button>
        <div class="full-chart" use:plotlyAction={{ view: selectedChart, isLarge: true }}></div>
      </div>
    </div>
  {/if}
</div>