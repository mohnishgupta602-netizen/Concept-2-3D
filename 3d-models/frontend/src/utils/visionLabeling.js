/**
 * Utility functions for capturing 3D model canvas and sending to Gemini for vision analysis
 */

import { apiUrl } from '../config/api';

export const captureCanvasAsBase64 = async (canvasElement) => {
  if (!canvasElement) {
    console.error('Canvas element is null or undefined');
    return null;
  }

  return new Promise((resolve) => {
    try {
      // Check if it's a canvas element with toDataURL method
      if (!canvasElement.toDataURL) {
        console.error('Element is not a valid canvas:', typeof canvasElement, canvasElement.constructor.name);
        resolve(null);
        return;
      }

      const dataUrl = canvasElement.toDataURL('image/png');
      if (!dataUrl) {
        console.error('toDataURL() returned empty string');
        resolve(null);
        return;
      }

      // Remove 'data:image/png;base64,' prefix
      const base64 = dataUrl.split(',')[1];
      if (!base64) {
        console.error('Failed to extract base64 data from dataUrl');
        resolve(null);
        return;
      }

      console.log(`✓ Canvas captured: ${base64.length} bytes of base64 data`);
      resolve(base64);
    } catch (err) {
      console.error('Canvas capture error:', err.message, err.stack);
      resolve(null);
    }
  });
};

/**
 * Get canvas from THREE.js renderer
 */
export const getCanvasFromRenderer = (rendererRef) => {
  if (!rendererRef || !rendererRef.current) return null;
  return rendererRef.current.domElement;
};

/**
 * Send model image to backend for Gemini vision-based label positioning
 */
export const optimizeLabelsWithVision = async (
  modelId,
  concept,
  partDefinitions,
  modelImageBase64
) => {
  if (!modelImageBase64) {
    console.error('❌ No image provided for vision analysis');
    return { error: 'Canvas capture failed - no image data', parts: null };
  }

  if (!partDefinitions || partDefinitions.length === 0) {
    console.error('❌ No part definitions provided');
    return { error: 'No parts to optimize', parts: null };
  }

  try {
    const endpoint = apiUrl('/labels/position-from-image');
    console.log(`📡 Sending vision optimization request to ${endpoint}`);
    console.log(`   Model ID: ${modelId}, Concept: ${concept}, Parts: ${partDefinitions.length}`);

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model_id: modelId,
        concept: concept || 'model',
        part_definitions: partDefinitions,
        model_image_base64: modelImageBase64
      })
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`❌ Backend error ${response.status}: ${errorText}`);
      return { error: `Backend error ${response.status}: ${errorText}`, parts: null };
    }

    const data = await response.json();
    console.log('✅ Vision optimization successful:', data);
    
    return {
      error: null,
      parts: data.updated_parts || partDefinitions
    };
  } catch (err) {
    console.error('❌ Vision optimization network error:', err.message, err.stack);
    return { error: `Network error: ${err.message}`, parts: null };
  }
};

/**
 * Trigger vision optimization for labels on demand
 */
export const triggerVisionOptimization = async (
  modelId,
  concept,
  partDefinitions,
  canvasElement
) => {
  console.log('🚀 Starting Gemini vision-based label positioning...');

  const imageBase64 = await captureCanvasAsBase64(canvasElement);

  if (!imageBase64) {
    console.error('❌ Failed to capture canvas image');
    return { error: 'Failed to capture canvas image', parts: null };
  }

  const result = await optimizeLabelsWithVision(
    modelId,
    concept,
    partDefinitions,
    imageBase64
  );

  if (result.error) {
    console.error('❌ Optimization failed:', result.error);
    return result;
  }

  console.log('✅ Optimization complete');
  return result;
};
