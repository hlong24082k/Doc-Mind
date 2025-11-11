"use client";

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { MadeWithDyad } from "@/components/made-with-dyad";

const Index = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // For now, redirect to the login page.
    // In a real app, you'd check authentication status here.
    navigate("/login");
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">Loading...</h1>
        <p className="text-xl text-gray-600">
          Redirecting to login page.
        </p>
      </div>
      <MadeWithDyad />
    </div>
  );
};

export default Index;