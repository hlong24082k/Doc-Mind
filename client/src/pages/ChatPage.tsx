import React, { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Send } from "lucide-react";
import { useParams, useLocation } from "react-router-dom";

interface Message {
  id: string;
  text: string;
  sender: "user" | "ai";
}

const ChatPage: React.FC = () => {
  const { documentId } = useParams<{ documentId: string }>();
  const location = useLocation();
  const documentName = location.state?.documentName || "No Document Selected";
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");

  useEffect(() => {
    // Reset messages when documentId changes
    setMessages([
      {
        id: "ai-welcome",
        text: `Hello! How can I help you with "${documentName}" today?`,
        sender: "ai",
      },
    ]);
  }, [documentId, documentName]);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputMessage.trim() === "") return;

    const newUserMessage: Message = {
      id: `user-${Date.now()}`,
      text: inputMessage,
      sender: "user",
    };
    setMessages((prevMessages) => [...prevMessages, newUserMessage]);
    setInputMessage("");

    // Simulate AI response
    setTimeout(() => {
      const aiResponse: Message = {
        id: `ai-${Date.now()}`,
        text: `I received your question about "${inputMessage}" regarding ${documentName}. I'm processing it now.`,
        sender: "ai",
      };
      setMessages((prevMessages) => [...prevMessages, aiResponse]);
    }, 1000);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b p-4">
        <h2 className="text-xl font-semibold">Chat with: {documentName}</h2>
        {documentId && <p className="text-sm text-muted-foreground">Document ID: {documentId}</p>}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${
              message.sender === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`p-3 rounded-lg max-w-[70%] ${
                message.sender === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-gray-200 dark:bg-gray-700"
              }`}
            >
              {message.text}
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={handleSendMessage} className="border-t p-4 flex items-center gap-2">
        <Input
          placeholder="Type your message..."
          className="flex-1"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
        />
        <Button type="submit" size="icon">
          <Send className="h-4 w-4" />
          <span className="sr-only">Send message</span>
        </Button>
      </form>
    </div>
  );
};

export default ChatPage;