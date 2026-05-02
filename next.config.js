const nextConfig = {
  trailingSlash: false,
  webpack: (config, { isServer }) => {
    // Add a rule to handle .glsl files
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/,
      exclude: /node_modules/,
      use: [
        {
          loader: "raw-loader",
        },
        {
          loader: "glslify-loader",
        },
      ],
    });

    return config;
  },
};

module.exports = nextConfig;
