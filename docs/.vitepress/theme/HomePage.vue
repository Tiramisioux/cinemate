<template>
    <div class="home-page">
      <div class="hero">
        <h1>Cinemate</h1>
        <p>Your project description goes here.</p>
        <a class="action-button" href="/docs/">Get Started</a>
      </div>
      <div class="features">
        <div class="feature">
          <h2>Feature One</h2>
          <p>Explanation of the first feature.</p>
        </div>
        <div class="feature">
          <h2>Feature Two</h2>
          <p>Explanation of the second feature.</p>
        </div>
        <div class="feature">
          <h2>Feature Three</h2>
          <p>Explanation of the third feature.</p>
        </div>
      </div>
    </div>
  </template>
  
  <script setup>
  // Additional script setup can go here if needed
  </script>
  
  <style scoped>
  .home-page {
    
    text-align: center;
    padding: 2rem;
  }
  
  .hero {
    margin-bottom: 3rem;
  }
  
  .hero h1 {
    font-size: 3rem;
    margin: 0;
  }
  
  .hero p {
    font-size: 1.25rem;
    color: #666;
  }
  
  .action-button {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    background-color: #42b983;
    color: white;
    border-radius: 0.25rem;
    text-decoration: none;
    font-size: 1rem;
    margin-top: 1rem;
  }
  
  .features {
    display: flex;
    justify-content: space-around;
  }
  
  .feature {
    width: 30%;
  }
  
  .feature h2 {
    font-size: 1.5rem;
  }
  
  .feature p {
    font-size: 1rem;
    color: #666;
  }
  </style>
  