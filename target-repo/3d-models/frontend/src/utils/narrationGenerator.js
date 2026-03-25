/**
 * Generate comprehensive narration for English audio description
 * Target duration: 90-120 seconds (approximately 300-400 words)
 */

export function generateNarration(topic, modelData, activeQuery) {
  if (!topic || !modelData) return '';

  // Extract available information
  const title = modelData.title || topic;
  const aiOverview = (modelData.ai_overview || '').trim();
  const source = modelData.source || '';
  const description = modelData.description || '';
  
  // Start building comprehensive narration
  let narration = '';

  // PART 1: Introduction (15-20 seconds)
  narration += `You searched for "${topic.toLowerCase()}". `;
  narration += `This visualization shows a three-dimensional representation of ${title}. `;

  // PART 2: Concept Clarity from AI Overview (45-60 seconds)
  if (aiOverview) {
    // Use Wikipedia summary if available
    narration += `Here's an overview: ${aiOverview}. `;
  } else {
    // Fallback: generate from available data
    narration += `${title} is an important concept in education and understanding. `;
    
    if (description) {
      narration += `${description}. `;
    } else {
      narration += `This three-dimensional model helps you visualize and understand the spatial properties and structure of ${title}. `;
    }
  }

  // PART 3: Interactive Features & How to Use (20-30 seconds)
  narration += `You can interact with this model by rotating it to view from different angles using your mouse or touch controls. `;
  narration += `You can also zoom in and out to examine specific parts in detail. `;
  
  if (modelData.part_definitions && modelData.part_definitions.length > 0) {
    const partCount = Math.min(modelData.part_definitions.length, 5);
    narration += `This model has ${partCount} labeled parts that you can hover over to explore. `;
  }

  // PART 4: Relevance & Source (15-20 seconds)
  if (modelData.score) {
    narration += `This model matches your search query with ${modelData.score} percent relevance. `;
  }
  
  if (source) {
    narration += `The source of this model is ${source}. `;
  }

  if (modelData.average_rating && modelData.average_rating > 0) {
    narration += `This model has been rated ${modelData.average_rating.toFixed(1)} out of 5 stars by other users. `;
  }

  // PART 5: Call to Action (10-15 seconds)
  narration += `Explore this visualization to enhance your understanding of ${title}. `;
  narration += `You can submit a rating and feedback to help other learners find the best models.`;

  return narration;
}

/**
 * Enhanced narration with detailed point structure
 * For more detailed exploration
 */
export function generateDetailedNarration(topic, modelData, activeQuery) {
  if (!topic || !modelData) return '';

  const title = modelData.title || topic;
  const aiOverview = (modelData.ai_overview || '').trim();
  const source = modelData.source || '';

  let narration = '';

  // Introduction
  narration += `Welcome. You are exploring a three-dimensional visualization of ${title}. `;
  narration += `This interactive model was created to help you understand the concepts, structures, and spatial relationships of ${topic.toLowerCase()} in an intuitive and engaging way. `;

  // Main concept explanation
  if (aiOverview) {
    narration += `Let's understand the core concept: ${aiOverview}. `;
  } else {
    narration += `${title} is a significant topic in education. `;
    narration += `This three-dimensional representation provides visual context and structure that helps accelerate learning and conceptual understanding. `;
  }

  // Key features of the model
  narration += `This model contains important labeled components. `;
  
  if (modelData.part_definitions && modelData.part_definitions.length > 0) {
    const totalParts = modelData.part_definitions.length;
    narration += `There are ${totalParts} distinct parts identified and labeled in this model. `;
    narration += `Each part is shown with a numbered label that you can interact with. `;
  }

  // Interaction guide
  narration += `You can explore this model by rotating it, zooming in to see details, and examining each labeled component. `;
  narration += `Hover your mouse over any numbered label to reveal the part name and additional information. `;

  // Quality and relevance
  if (modelData.score) {
    narration += `This model achieved a ${modelData.score} percent match to your search query. `;
  }

  if (modelData.average_rating && modelData.average_rating > 0) {
    const stars = modelData.average_rating.toFixed(1);
    narration += `The community has rated this model ${stars} stars out of five. `;
  }

  narration += `This indicates high relevance and quality. `;

  // Source and attribution
  if (source) {
    narration += `This model was sourced from ${source}. `;
  }

  // Educational value
  narration += `Use this visualization to supplement your learning. `;
  narration += `Rotate the model, examine the labeled parts, and take time to understand how each component relates to the overall concept of ${topic.toLowerCase()}. `;

  // Engagement
  narration += `You can also rate this model and provide feedback to help other learners discover the most helpful visualizations. `;
  narration += `Enjoy exploring!`;

  return narration;
}

/**
 * Calculate approximate reading time in seconds
 * Average speaking speed: ~150 words per minute
 */
export function calculateNarrationDuration(text) {
  if (!text) return 0;
  const wordCount = text.trim().split(/\s+/).length;
  const durationSeconds = (wordCount / 150) * 60;
  return Math.round(durationSeconds);
}

/**
 * Truncate narration to fit time constraint (90-120 seconds)
 */
export function truncateNarrationToTime(text, minSeconds = 90, maxSeconds = 120) {
  if (!text) return '';

  const words = text.trim().split(/\s+/);
  const avgWordsPerSecond = 150 / 60; // At 150 WPM

  // Calculate target word count (middle of range)
  const targetSeconds = (minSeconds + maxSeconds) / 2;
  const targetWords = Math.round(targetSeconds * avgWordsPerSecond);

  if (words.length <= targetWords) {
    return text; // Already within limit
  }

  // Find the best cutoff point (at sentence boundary if possible)
  let truncated = words.slice(0, targetWords).join(' ');

  // Find last sentence boundary
  const lastPeriod = truncated.lastIndexOf('.');
  const lastQuestion = truncated.lastIndexOf('?');
  const lastExclamation = truncated.lastIndexOf('!');

  const lastBoundary = Math.max(lastPeriod, lastQuestion, lastExclamation);

  if (lastBoundary > targetWords * 0.7) {
    truncated = truncated.substring(0, lastBoundary + 1);
  } else {
    truncated += '.';
  }

  return truncated;
}
